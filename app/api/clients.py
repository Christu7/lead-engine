from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_token_data, require_admin
from app.core.security import TokenData
from app.models.user import User, UserClient
from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate
from app.services import client as client_service
from app.services.auth import get_user_clients

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
)


@router.get("/me", response_model=ClientResponse)
async def get_my_client(
    token_data: TokenData = Depends(get_token_data),
    db: AsyncSession = Depends(get_db),
):
    """Return the currently active client from the JWT."""
    if token_data.active_client_id is None:
        raise HTTPException(status_code=404, detail="No active client")
    client = await client_service.get_client(db, token_data.active_client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.post("/", response_model=ClientResponse, status_code=201)
async def create_client(
    data: ClientCreate,
    token_data: TokenData = Depends(require_admin),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new client. Admin only."""
    client = await client_service.create_client(db, data)
    # Auto-assign the creating admin to the new client
    db.add(UserClient(user_id=current_user.id, client_id=client.id))
    await db.commit()
    return client


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    token_data: TokenData = Depends(get_token_data),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
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
    token_data: TokenData = Depends(get_token_data),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    clients = await get_user_clients(db, current_user.id, current_user.role)
    if not any(c.id == client_id for c in clients):
        raise HTTPException(status_code=403, detail="Access denied")
    client = await client_service.update_client(db, client_id, data)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: int,
    token_data: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a client. Admin only."""
    deleted = await client_service.delete_client(db, client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Client not found")
