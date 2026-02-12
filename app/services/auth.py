from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.user import ApiKey, User


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


async def get_api_key(db: AsyncSession, key: str) -> ApiKey | None:
    result = await db.execute(
        select(ApiKey).where(ApiKey.key == key, ApiKey.is_active == True)  # noqa: E712
    )
    return result.scalar_one_or_none()
