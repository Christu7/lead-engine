import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.redis import redis as redis_client
from app.core.security import hash_password
from app.models.client import Client
from app.models.user import User, UserClient
from app.schemas.admin import AdminCreateUser, AdminUserResponse, AssignClientRequest
from app.services.ai_enrichment import run_analysis_for_lead
from app.services.auth import get_user_by_email
from app.services.dead_letter import DeadLetterService, DeadLetterType
from app.services.enrichment.queue import QUEUE_KEY

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserResponse], dependencies=[Depends(require_admin)])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.id))
    return list(result.scalars().all())


@router.post("/users", response_model=AdminUserResponse, status_code=201, dependencies=[Depends(require_admin)])
async def create_user(data: AdminCreateUser, db: AsyncSession = Depends(get_db)):
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


@router.post("/users/{user_id}/clients", status_code=201, dependencies=[Depends(require_admin)])
async def assign_client(user_id: int, body: AssignClientRequest, db: AsyncSession = Depends(get_db)):
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


@router.delete("/users/{user_id}/clients/{client_id}", status_code=204, dependencies=[Depends(require_admin)])
async def unassign_client(user_id: int, client_id: int, db: AsyncSession = Depends(get_db)):
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


@router.get("/dead-letters", dependencies=[Depends(require_admin)])
async def list_dead_letters():
    """List all entries currently in the dead letter queue, newest first."""
    svc = DeadLetterService(redis_client)
    entries = await svc.list()
    return {"count": len(entries), "dead_letters": entries}


@router.post("/dead-letters/{entry_id}/retry", dependencies=[Depends(require_admin)])
async def retry_dead_letter(
    entry_id: str,
    background_tasks: BackgroundTasks,
):
    """Re-queue a dead letter entry for reprocessing, then dismiss it."""
    svc = DeadLetterService(redis_client)
    entry = await svc.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Dead letter entry not found")

    dl_type = entry.get("type")
    lead_id = entry["lead_id"]
    client_id = entry["client_id"]

    if dl_type == DeadLetterType.ENRICHMENT:
        payload = json.dumps({"lead_id": lead_id, "client_id": client_id})
        await redis_client.lpush(QUEUE_KEY, payload)
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
