import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_token_data, require_admin, require_superadmin
from app.core.redis import redis as redis_client
from app.core.security import TokenData, hash_password
from app.models.client import Client
from app.models.company import Company
from app.models.lead import Lead
from app.models.user import User, UserClient
from app.schemas.admin import (
    AdminClientResponse,
    AdminCreateUser,
    AdminUpdateClient,
    AdminUpdateUser,
    AdminUserClientInfo,
    AdminUserResponse,
    AssignClientRequest,
)

logger = logging.getLogger(__name__)
from app.services.ai_enrichment import run_analysis_for_lead
from app.services.auth import get_user_by_email, invalidate_user_tokens
from app.services.dead_letter import DeadLetterService, DeadLetterType
from app.services import task_queue

router = APIRouter(prefix="/admin", tags=["admin"])

_VALID_ROLES = frozenset(["member", "admin", "superadmin"])


async def _build_user_response(db: AsyncSession, user: User) -> AdminUserResponse:
    """Build AdminUserResponse with workspace list for a single user."""
    result = await db.execute(
        select(Client.id, Client.name)
        .join(UserClient, Client.id == UserClient.client_id)
        .where(UserClient.user_id == user.id)
        .order_by(Client.id)
    )
    clients = [AdminUserClientInfo(id=row.id, name=row.name) for row in result]
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
        clients=clients,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    current_user: User = Depends(require_admin),
    token_data: TokenData = Depends(get_token_data),
    db: AsyncSession = Depends(get_db),
):
    """Superadmin sees all users with their workspaces. Admin sees only users in their active client."""
    if current_user.role == "superadmin":
        result = await db.execute(select(User).order_by(User.id))
        users = list(result.scalars().all())
    else:
        # Per-client admin: return users assigned to the current active client only.
        if token_data.active_client_id is None:
            return []
        result = await db.execute(
            select(User)
            .join(UserClient, User.id == UserClient.user_id)
            .where(UserClient.client_id == token_data.active_client_id)
            .distinct()
            .order_by(User.id)
        )
        users = list(result.scalars().all())

    return [await _build_user_response(db, u) for u in users]


@router.post("/users", response_model=AdminUserResponse, status_code=201)
async def create_user(
    data: AdminCreateUser,
    current_user: User = Depends(require_admin),
    token_data: TokenData = Depends(get_token_data),
    db: AsyncSession = Depends(get_db),
):
    # Admins can only set member/admin; superadmin can set any role.
    allowed = {"member", "admin"} if current_user.role == "admin" else _VALID_ROLES
    if data.role not in allowed:
        raise HTTPException(status_code=400, detail=f"Role '{data.role}' not allowed for your permission level")
    existing = await get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=data.email,
        name=data.name or None,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    await db.flush()  # populate user.id before adding UserClient rows

    # Validate and assign workspaces.
    client_ids = list(dict.fromkeys(data.client_ids))  # deduplicate, preserve order
    for cid in client_ids:
        # Admins may only assign to their own client.
        if current_user.role == "admin" and cid != token_data.active_client_id:
            raise HTTPException(
                status_code=403,
                detail=f"Admin can only assign users to their own workspace (client_id={token_data.active_client_id})",
            )
        client_obj = await db.get(Client, cid)
        if client_obj is None or not client_obj.is_active:
            raise HTTPException(status_code=400, detail=f"Workspace {cid} not found or inactive")
        db.add(UserClient(user_id=user.id, client_id=cid))

    await db.commit()
    await db.refresh(user)
    logger.info(
        "User created",
        extra={"user_id": user.id, "email": user.email, "role": user.role, "client_ids": client_ids},
    )
    return await _build_user_response(db, user)


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: int,
    body: AdminUpdateUser,
    current_user: User = Depends(require_admin),
    token_data: TokenData = Depends(get_token_data),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's name, role, and/or active status.

    Guards:
    - Cannot change own role or deactivate own account.
    - Admin can only modify users in their active workspace.
    - Admin cannot promote/modify a superadmin.
    """
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Admin scope: cannot touch superadmins, must share a workspace with target.
    if current_user.role == "admin":
        if target.role == "superadmin":
            raise HTTPException(status_code=403, detail="Cannot modify a superadmin")
        if token_data.active_client_id is not None:
            access = await db.execute(
                select(UserClient).where(
                    UserClient.user_id == user_id,
                    UserClient.client_id == token_data.active_client_id,
                )
            )
            if access.scalar_one_or_none() is None:
                raise HTTPException(status_code=403, detail="You can only modify users in your workspace")

    # Self-modification guards.
    if user_id == current_user.id:
        if body.role is not None and body.role != current_user.role:
            raise HTTPException(status_code=400, detail="Cannot change your own role")
        if body.is_active is False:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    should_invalidate = False

    if body.name is not None:
        target.name = body.name.strip() or None

    if body.role is not None:
        allowed = {"member", "admin"} if current_user.role == "admin" else _VALID_ROLES
        if body.role not in allowed:
            raise HTTPException(status_code=400, detail=f"Role '{body.role}' not allowed for your permission level")
        if body.role != target.role:
            target.role = body.role
            should_invalidate = True

    if body.is_active is not None:
        target.is_active = body.is_active

    await db.commit()
    await db.refresh(target)

    if should_invalidate:
        await invalidate_user_tokens(db, user_id)

    logger.info(
        "User updated",
        extra={"user_id": user_id, "updated_by": current_user.id, "changes": body.model_dump(exclude_none=True)},
    )
    return await _build_user_response(db, target)



@router.post("/users/{user_id}/clients", status_code=201)
async def assign_client(
    user_id: int,
    body: AssignClientRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # MT-2: non-superadmin admins may only assign users to clients they belong to.
    if current_user.role != "superadmin":
        access_check = await db.execute(
            select(UserClient).where(
                UserClient.user_id == current_user.id,
                UserClient.client_id == body.client_id,
            )
        )
        if access_check.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="You do not have access to that client")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    client_result = await db.execute(select(Client).where(Client.id == body.client_id))
    if client_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Client not found")

    existing = await db.execute(
        select(UserClient).where(
            UserClient.user_id == user_id,
            UserClient.client_id == body.client_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User already assigned to that client")

    db.add(UserClient(user_id=user_id, client_id=body.client_id))
    await db.commit()
    return {"user_id": user_id, "client_id": body.client_id}


@router.delete("/users/{user_id}/clients/{client_id}", status_code=204)
async def unassign_client(
    user_id: int,
    client_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # MT-2: non-superadmin admins may only unassign users from clients they belong to.
    if current_user.role != "superadmin":
        access_check = await db.execute(
            select(UserClient).where(
                UserClient.user_id == current_user.id,
                UserClient.client_id == client_id,
            )
        )
        if access_check.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="You do not have access to that client")

    result = await db.execute(
        select(UserClient).where(
            UserClient.user_id == user_id,
            UserClient.client_id == client_id,
        )
    )
    uc = result.scalar_one_or_none()
    if uc is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    await db.delete(uc)
    await db.commit()
    # P1-2: bump token_version so any JWT the removed user holds is immediately rejected.
    await invalidate_user_tokens(db, user_id)


async def _build_client_response(db: AsyncSession, client: Client) -> AdminClientResponse:
    """Build AdminClientResponse with live counts for a single client."""
    user_count_sq = (
        select(func.count(UserClient.user_id))
        .where(UserClient.client_id == client.id)
        .scalar_subquery()
    )
    lead_count_sq = (
        select(func.count(Lead.id))
        .where(Lead.client_id == client.id)
        .scalar_subquery()
    )
    company_count_sq = (
        select(func.count(Company.id))
        .where(Company.client_id == client.id)
        .scalar_subquery()
    )
    row = await db.execute(
        select(user_count_sq, lead_count_sq, company_count_sq)
    )
    user_count, lead_count, company_count = row.one()
    return AdminClientResponse(
        id=client.id,
        name=client.name,
        description=client.description,
        is_active=client.is_active,
        user_count=user_count,
        lead_count=lead_count,
        company_count=company_count,
        created_at=client.created_at,
    )


@router.get("/clients", response_model=list[AdminClientResponse])
async def list_clients(
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Superadmin only — list all clients (including inactive) with counts."""
    result = await db.execute(select(Client).order_by(Client.id))
    clients = result.scalars().all()

    # Fetch counts for all clients in one pass using correlated subqueries per row.
    # The list is typically small (tens of workspaces) so N round-trips are fine.
    responses = []
    for client in clients:
        responses.append(await _build_client_response(db, client))
    return responses


@router.patch("/clients/{client_id}", response_model=AdminClientResponse)
async def update_client_admin(
    client_id: int,
    body: AdminUpdateClient,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> AdminClientResponse:
    """Rename or re-describe a workspace. Superadmin only."""
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        # Uniqueness check (case-insensitive, excluding self)
        existing = await db.execute(
            select(Client).where(
                func.lower(Client.name) == name.lower(),
                Client.id != client_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"A workspace named '{name}' already exists",
            )
        client.name = name

    if body.description is not None:
        client.description = body.description or None

    await db.commit()
    await db.refresh(client)
    logger.info(
        "Workspace updated",
        extra={"client_id": client_id, "name": client.name},
    )
    return await _build_client_response(db, client)


@router.delete("/clients/{client_id}", status_code=204)
async def delete_client_admin(
    client_id: int,
    token_data: TokenData = Depends(get_token_data),
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a workspace. Superadmin only.

    Guards:
    - Cannot delete the last active workspace.
    - Cannot delete the workspace the requesting user is currently active in.

    Side-effects:
    - UserClient rows for users whose ONLY workspace is this one are removed
      (those users become unassigned). Their token_version is bumped to
      invalidate outstanding JWTs.
    - All other UserClient rows for this workspace are also removed.
    """
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not client.is_active:
        raise HTTPException(status_code=409, detail="Workspace is already inactive")

    # Guard: cannot delete while it is the requester's active workspace
    if token_data.active_client_id == client_id:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete your currently active workspace. Switch to another workspace first.",
        )

    # Guard: must leave at least one active workspace
    active_count_result = await db.execute(
        select(func.count(Client.id)).where(Client.is_active == True)  # noqa: E712
    )
    active_count = active_count_result.scalar_one()
    if active_count <= 1:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete the last active workspace.",
        )

    # Find users assigned ONLY to this workspace (will become unassigned)
    sole_users_result = await db.execute(
        select(UserClient.user_id)
        .where(
            UserClient.user_id.in_(
                select(UserClient.user_id).where(UserClient.client_id == client_id)
            ),
            UserClient.client_id != client_id,
        )
    )
    users_with_other_clients = {row.user_id for row in sole_users_result}

    all_users_result = await db.execute(
        select(UserClient.user_id).where(UserClient.client_id == client_id)
    )
    all_users_in_client = {row.user_id for row in all_users_result}
    sole_user_ids = all_users_in_client - users_with_other_clients
    affected_count = len(sole_user_ids)

    if affected_count:
        logger.warning(
            "Workspace deletion leaving %d user(s) unassigned",
            affected_count,
            extra={"client_id": client_id, "sole_user_ids": list(sole_user_ids)},
        )
        # Invalidate their tokens so they cannot use stale JWTs
        for user_id in sole_user_ids:
            from app.services.auth import invalidate_user_tokens
            await invalidate_user_tokens(db, user_id)

    # Remove all UserClient rows for this workspace
    all_uc_result = await db.execute(
        select(UserClient).where(UserClient.client_id == client_id)
    )
    for uc in all_uc_result.scalars().all():
        await db.delete(uc)

    # Soft-delete
    client.is_active = False
    await db.commit()

    logger.info(
        "Workspace soft-deleted",
        extra={
            "client_id": client_id,
            "name": client.name,
            "affected_users": affected_count,
        },
    )


@router.get("/queue-stats", dependencies=[Depends(require_superadmin)])
async def get_queue_stats():
    """Return current task queue statistics. Superadmin only."""
    q_stats = await task_queue.stats()
    svc = DeadLetterService(redis_client)
    dead_letters = await svc.list()
    return {**q_stats, "dead_letter": len(dead_letters)}


@router.get("/dead-letters")
async def list_dead_letters(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List dead letter entries visible to the requesting admin, newest first.

    Superadmin sees all entries. Per-client admins see only entries belonging
    to clients they are assigned to.
    """
    if current_user.role == "superadmin":
        client_ids = None  # no filter
    else:
        rows = await db.execute(
            select(UserClient.client_id).where(UserClient.user_id == current_user.id)
        )
        client_ids = list(rows.scalars().all())

    svc = DeadLetterService(redis_client)
    entries = await svc.list(client_ids=client_ids)
    return {"count": len(entries), "dead_letters": entries}


@router.post("/dead-letters/{entry_id}/retry")
async def retry_dead_letter(
    entry_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Re-queue a dead letter entry for reprocessing, then dismiss it."""
    svc = DeadLetterService(redis_client)
    entry = await svc.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Dead letter entry not found")

    dl_type = entry.get("type")
    lead_id = entry.get("lead_id")
    client_id = entry.get("client_id")
    if lead_id is None or client_id is None:
        raise HTTPException(
            status_code=400,
            detail="Dead letter entry is malformed: missing lead_id or client_id",
        )

    # MT-1: verify the requesting admin has access to this entry's client.
    if current_user.role != "superadmin":
        access_check = await db.execute(
            select(UserClient).where(
                UserClient.user_id == current_user.id,
                UserClient.client_id == client_id,
            )
        )
        if access_check.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="You do not have access to this dead letter entry")

    if dl_type == DeadLetterType.ENRICHMENT:
        await task_queue.enqueue(
            "lead_enrichment",
            {"lead_id": lead_id, "client_id": client_id, "retry_count": 0},
        )
    elif dl_type == DeadLetterType.AI_ANALYSIS:
        background_tasks.add_task(run_analysis_for_lead, lead_id, client_id)
    elif dl_type == DeadLetterType.ROUTING:
        background_tasks.add_task(_retry_routing_background, lead_id, client_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported dead letter type: {dl_type}")

    await svc.dismiss(entry_id)
    return {"retried": entry_id, "type": dl_type, "lead_id": lead_id}


@router.delete("/dead-letters/{entry_id}", status_code=204, dependencies=[Depends(require_admin)])
async def dismiss_dead_letter(entry_id: str):
    """Remove a dead letter entry without retrying."""
    svc = DeadLetterService(redis_client)
    found = await svc.dismiss(entry_id)
    if not found:
        raise HTTPException(status_code=404, detail="Dead letter entry not found")


async def _retry_routing_background(lead_id: int, client_id: int) -> None:
    """Background task: re-run routing for a single lead."""
    import logging

    from app.core.database import async_session
    from app.models.lead import Lead
    from app.services.routing import route_lead

    _logger = logging.getLogger(__name__)
    try:
        async with async_session() as db:
            lead = await db.get(Lead, lead_id)
            if lead is None or lead.client_id != client_id:
                _logger.error(
                    "Routing retry: lead %d not found or client mismatch",
                    lead_id,
                    extra={"lead_id": lead_id, "client_id": client_id},
                )
                return
            await route_lead(db, lead, client_id)
            await db.commit()
    except Exception:
        _logger.exception(
            "Routing retry failed for lead %d",
            lead_id,
            extra={"lead_id": lead_id, "client_id": client_id},
        )
