from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_id, get_current_active_user, require_admin, require_superadmin
from app.models.user import User
from app.schemas.client import ClientCreate, ClientPublicResponse, ClientResponse, ClientUpdate
from app.services import client as client_service
from app.services.auth import get_user_clients

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
)


@router.get("/me", response_model=ClientPublicResponse)
async def get_my_client(
    client_id: int = Depends(get_client_id),
    _current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the currently active client for the authenticated user.

    Uses get_client_id so the user must be active, the client must be active,
    and the user must still hold a membership row in user_clients.
    Settings are excluded from the response — use /api/settings for those.
    """
    client = await client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.post("/", response_model=ClientResponse, status_code=201)
async def create_client(
    data: ClientCreate,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new client. Superadmin only."""
    client = await client_service.create_client(db, data)
    await db.commit()
    return client


@router.get("/{client_id}", response_model=ClientPublicResponse)
async def get_client(
    client_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return public info for a client the caller belongs to.

    Settings are excluded — use /api/settings to read enrichment or routing config.
    """
    clients = await get_user_clients(db, current_user.id, current_user.role)
    if not any(c.id == client_id for c in clients):
        raise HTTPException(status_code=403, detail="Access denied")
    client = await client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    data: ClientUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a client. Admin or superadmin only.

    Changing is_active is further restricted to superadmin.
    Returns the full response including settings so the caller can verify what changed.
    """
    clients = await get_user_clients(db, current_user.id, current_user.role)
    if not any(c.id == client_id for c in clients):
        raise HTTPException(status_code=403, detail="Access denied")
    if data.is_active is not None and current_user.role != "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Only superadmins can activate or deactivate a client workspace.",
        )
    client = await client_service.update_client(db, client_id, data)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: int,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a client. Superadmin only."""
    deleted = await client_service.delete_client(db, client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Client not found")
