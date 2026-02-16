from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.schemas.client import ClientCreate, ClientListResponse, ClientResponse, ClientUpdate
from app.services import client as client_service

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
    dependencies=[Depends(get_current_active_user)],
)


@router.post("/", response_model=ClientResponse, status_code=201)
async def create_client(data: ClientCreate, db: AsyncSession = Depends(get_db)):
    client = await client_service.create_client(db, data)
    return client


@router.get("/", response_model=ClientListResponse)
async def list_clients(db: AsyncSession = Depends(get_db)):
    items, total = await client_service.list_clients(db)
    return ClientListResponse(items=items, total=total)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(client_id: int, db: AsyncSession = Depends(get_db)):
    client = await client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(client_id: int, data: ClientUpdate, db: AsyncSession = Depends(get_db)):
    client = await client_service.update_client(db, client_id, data)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.delete("/{client_id}", status_code=204)
async def delete_client(client_id: int, db: AsyncSession = Depends(get_db)):
    deleted = await client_service.delete_client(db, client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Client not found")
