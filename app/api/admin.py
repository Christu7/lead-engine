from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_token_data, require_admin, require_superadmin
from app.core.redis import redis as redis_client
from app.core.security import TokenData, hash_password
from app.models.client import Client
from app.models.user import User, UserClient
from app.schemas.admin import (
    AdminClientResponse,
    AdminCreateUser,
    AdminUpdateUserRole,
    AdminUserResponse,
    AssignClientRequest,
)
from app.services.ai_enrichment import run_analysis_for_lead
from app.services.auth import get_user_by_email, invalidate_user_tokens
from app.services.dead_letter import DeadLetterService, DeadLetterType
from app.services import task_queue

router = APIRouter(prefix="/admin", tags=["admin"])

_VALID_ROLES = frozenset(["member", "admin", "superadmin"])


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    current_user: User = Depends(require_admin),
    token_data: TokenData = Depends(get_token_data),
    db: AsyncSession = Depends(get_db),
):
    """Superadmin sees all users. Admin sees only users in their active client."""
    if current_user.role == "superadmin":
        result = await db.execute(select(User).order_by(User.id))
        return list(result.scalars().all())

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
    return list(result.scalars().all())


@router.post("/users", response_model=AdminUserResponse, status_code=201)
async def create_user(
    data: AdminCreateUser,
    current_user: User = Depends(require_admin),
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
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}/role", response_model=AdminUserResponse)
async def update_user_role(
    user_id: int,
    body: AdminUpdateUserRole,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Change a user's role. Admins can set member/admin. Superadmin can set any role."""
    allowed = {"member", "admin"} if current_user.role == "admin" else _VALID_ROLES
    if body.role not in allowed:
        raise HTTPException(status_code=400, detail=f"Role '{body.role}' not allowed for your permission level")

    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent a regular admin from modifying a superadmin
    if current_user.role == "admin" and target.role == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot modify a superadmin")

    target.role = body.role
    await db.commit()
    await db.refresh(target)
    return target


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


@router.get("/clients", response_model=list[AdminClientResponse])
async def list_clients(
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Superadmin only — list all clients with user counts."""
    rows = await db.execute(
        select(Client, func.count(UserClient.user_id).label("user_count"))
        .outerjoin(UserClient, Client.id == UserClient.client_id)
        .group_by(Client.id)
        .order_by(Client.id)
    )
    return [
        AdminClientResponse(
            id=client.id,
            name=client.name,
            user_count=count,
            created_at=client.created_at,
        )
        for client, count in rows.all()
    ]


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
