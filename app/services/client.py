from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.schemas.client import ClientCreate, ClientUpdate


async def create_client(db: AsyncSession, data: ClientCreate) -> Client:
    client = Client(**data.model_dump())
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return client


async def get_client(db: AsyncSession, client_id: int) -> Client | None:
    return await db.get(Client, client_id)


async def list_clients(db: AsyncSession) -> tuple[list[Client], int]:
    count_query = select(func.count()).select_from(Client)
    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(select(Client).order_by(Client.id))
    return list(result.scalars().all()), total


async def update_client(db: AsyncSession, client_id: int, data: ClientUpdate) -> Client | None:
    client = await db.get(Client, client_id)
    if client is None:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(client, key, value)
    await db.commit()
    await db.refresh(client)
    return client


async def delete_client(db: AsyncSession, client_id: int) -> bool:
    client = await db.get(Client, client_id)
    if client is None:
        return False
    await db.delete(client)
    await db.commit()
    return True
