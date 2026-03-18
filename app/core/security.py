from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass
class TokenData:
    user_id: int
    email: str
    role: str
    active_client_id: int | None


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: int,
    email: str,
    role: str,
    active_client_id: int | None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": email,
        "user_id": user_id,
        "role": role,
        "active_client_id": active_client_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> TokenData | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        user_id = payload.get("user_id")
        if email is None or user_id is None:
            return None
        return TokenData(
            user_id=user_id,
            email=email,
            role=payload.get("role", "member"),
            active_client_id=payload.get("active_client_id"),
        )
    except JWTError:
        return None
