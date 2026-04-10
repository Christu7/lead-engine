from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenData, decode_access_token
from app.models.client import Client
from app.models.user import ApiKey, User, UserClient
from app.services.auth import get_api_key as get_api_key_from_db
from app.services.auth import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_token_data(token: str = Depends(oauth2_scheme)) -> TokenData:
    data = decode_access_token(token)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return data


async def get_current_user(
    token_data: TokenData = Depends(get_token_data),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_user_by_id(db, token_data.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Reject tokens issued before the last logout / token invalidation.
    if token_data.token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
        )
    return user


async def get_client_id(
    token_data: TokenData = Depends(get_token_data),
    db: AsyncSession = Depends(get_db),
) -> int:
    """Resolve and validate the JWT's active_client_id.

    Verifies:
    - client exists and is active (not deactivated)
    - for admin/member: the user still has an explicit membership row (user_clients)
    - superadmin: access to any active client without membership check
    """
    if token_data.active_client_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active client. Contact your administrator.",
        )

    client_id = token_data.active_client_id

    client = await db.get(Client, client_id)
    if client is None or not client.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client workspace is inactive or no longer exists.",
        )

    # Superadmin has implicit access to every active client
    if token_data.role == "superadmin":
        return client_id

    # Admin/member: verify the user still has an explicit membership row
    result = await db.execute(
        select(UserClient).where(
            UserClient.user_id == token_data.user_id,
            UserClient.client_id == client_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this client workspace has been revoked.",
        )

    return client_id


async def require_admin(
    token_data: TokenData = Depends(get_token_data),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Allow admin OR superadmin. Members receive 403."""
    if token_data.role not in ("admin", "superadmin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    # Verify the user still exists and is active — JWT alone is not enough
    user = await get_user_by_id(db, token_data.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is disabled",
        )
    if token_data.token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_superadmin(
    token_data: TokenData = Depends(get_token_data),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Allow superadmin only. Admins and members receive 403."""
    if token_data.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required",
        )
    user = await get_user_by_id(db, token_data.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is disabled",
        )
    if token_data.token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def _get_api_key_obj(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """Validate the X-Api-Key header and return the ApiKey record."""
    api_key = await get_api_key_from_db(db, x_api_key)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )
    return api_key


async def get_api_key_auth(
    api_key: ApiKey = Depends(_get_api_key_obj),
) -> None:
    """Router-level guard: requires a valid API key (does not resolve client_id)."""


async def get_client_id_from_api_key(
    api_key: ApiKey = Depends(_get_api_key_obj),
    db: AsyncSession = Depends(get_db),
) -> int:
    """Resolve client_id from an API key and verify the client is still active."""
    if api_key.client_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This API key is not linked to a client. Contact your administrator.",
        )

    client = await db.get(Client, api_key.client_id)
    if client is None or not client.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client workspace is inactive or no longer exists.",
        )

    return api_key.client_id
