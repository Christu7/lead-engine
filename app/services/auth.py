from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.client import Client
from app.models.user import ApiKey, User, UserClient


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if user is None:
        return None
    if not user.hashed_password:
        return None  # OAuth-only account; no password set
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


async def find_or_create_google_user(db: AsyncSession, email: str, google_id: str) -> User:
    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()
    if user:
        return user

    # Existing email/password account — link the Google ID
    user = await get_user_by_email(db, email)
    if user:
        user.google_id = google_id
        await db.commit()
        await db.refresh(user)
        return user

    # New user via Google
    user = User(email=email, google_id=google_id, hashed_password=None, role="member")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_clients(db: AsyncSession, user_id: int, role: str) -> list[Client]:
    """Return all clients this user can access (admins see all clients)."""
    if role == "admin":
        result = await db.execute(select(Client).order_by(Client.id))
    else:
        result = await db.execute(
            select(Client)
            .join(UserClient, Client.id == UserClient.client_id)
            .where(UserClient.user_id == user_id)
            .order_by(Client.id)
        )
    return list(result.scalars().all())


async def get_default_client_id(db: AsyncSession, user_id: int, role: str) -> int | None:
    clients = await get_user_clients(db, user_id, role)
    return clients[0].id if clients else None


async def get_api_key(db: AsyncSession, key: str) -> ApiKey | None:
    result = await db.execute(
        select(ApiKey).where(ApiKey.key == key, ApiKey.is_active == True)  # noqa: E712
    )
    return result.scalar_one_or_none()
