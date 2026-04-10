from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.user import ApiKey, User, UserClient
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

    update_dict = data.model_dump(exclude_unset=True)
    deactivating = update_dict.get("is_active") is False and client.is_active

    for key, value in update_dict.items():
        setattr(client, key, value)

    if deactivating:
        # Revoke all user tokens for this client by bumping token_version.
        # This invalidates every JWT that was issued before deactivation.
        user_ids = list(
            (
                await db.execute(
                    select(UserClient.user_id).where(UserClient.client_id == client_id)
                )
            ).scalars()
        )
        if user_ids:
            await db.execute(
                sa_update(User)
                .where(User.id.in_(user_ids))
                .values(token_version=User.token_version + 1)
            )

        # Deactivate every API key linked to this client.
        await db.execute(
            sa_update(ApiKey)
            .where(ApiKey.client_id == client_id)
            .values(is_active=False)
        )

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
