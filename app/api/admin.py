from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.security import hash_password
from app.models.lead import Lead, RoutingLog
from app.models.user import User, UserClient
from app.schemas.admin import AdminCreateUser, AdminUserResponse, AssignClientRequest
from app.services.auth import get_user_by_email

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
async def list_dead_letters(db: AsyncSession = Depends(get_db)):
    """
    List leads stuck in a failed state — either enrichment failed or
    at least one routing attempt failed (while enrichment succeeded).
    """
    # Leads where enrichment itself failed
    failed_enrichment = list(
        (
            await db.execute(
                select(Lead)
                .where(Lead.enrichment_status == "failed")
                .order_by(Lead.updated_at.desc())
                .limit(200)
            )
        ).scalars().all()
    )

    # Leads where enrichment succeeded but routing failed (at least once)
    failed_routing = list(
        (
            await db.execute(
                select(Lead)
                .join(RoutingLog, Lead.id == RoutingLog.lead_id)
                .where(Lead.enrichment_status == "enriched", RoutingLog.success.is_(False))
                .group_by(Lead.id)
                .order_by(Lead.updated_at.desc())
                .limit(200)
            )
        ).scalars().all()
    )

    seen: set[int] = set()
    dead_letters = []
    for lead in failed_enrichment + failed_routing:
        if lead.id in seen:
            continue
        seen.add(lead.id)
        dead_letters.append(
            {
                "id": lead.id,
                "client_id": lead.client_id,
                "email": lead.email,
                "name": lead.name,
                "enrichment_status": lead.enrichment_status,
                "created_at": lead.created_at.isoformat(),
                "updated_at": lead.updated_at.isoformat(),
            }
        )

    return {"count": len(dead_letters), "dead_letters": dead_letters}
