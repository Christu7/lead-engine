import time

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_active_user, get_token_data
from app.core.redis import redis as redis_client
from app.core.security import TokenData, create_access_token
from app.models.user import User, UserClient
from app.schemas.auth import ClientInfo, TokenResponse, UserResponse
from app.services.auth import (
    authenticate_user,
    find_or_create_google_user,
    get_default_client_id,
    get_user_clients,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_LOGIN_RATE_LIMIT = 5   # attempts
_LOGIN_WINDOW_SEC = 60  # per minute


async def _check_login_rate_limit(request: Request) -> None:
    """Sliding-window rate limiter: max 5 login attempts per minute per source IP."""
    client_ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:login:{client_ip}"
    now = time.time()
    window_start = now - _LOGIN_WINDOW_SEC

    # Check count without recording — matches the fix in rate_limiter.py
    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zcard(key)
    results = await pipe.execute()

    if results[1] >= _LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again in a minute.",
        )

    pipe = redis_client.pipeline()
    pipe.zadd(key, {str(now): now})
    pipe.expire(key, _LOGIN_WINDOW_SEC)
    await pipe.execute()

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def _issue_token(user: User, active_client_id: int | None) -> str:
    return create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        active_client_id=active_client_id,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_check_login_rate_limit),
):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    active_client_id = await get_default_client_id(db, user.id, user.role)
    token = _issue_token(user, active_client_id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(
    token_data: TokenData = Depends(get_token_data),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    clients = await get_user_clients(db, current_user.id, current_user.role)
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        active_client_id=token_data.active_client_id,
        clients=[ClientInfo(id=c.id, name=c.name) for c in clients],
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )


@router.post("/switch-client/{client_id}", response_model=TokenResponse)
async def switch_client(
    client_id: int,
    token_data: TokenData = Depends(get_token_data),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Issue a new JWT with active_client_id set to the requested client."""
    clients = await get_user_clients(db, current_user.id, current_user.role)
    if not any(c.id == client_id for c in clients):
        raise HTTPException(status_code=403, detail="You don't have access to that client")
    token = _issue_token(current_user, client_id)
    return TokenResponse(access_token=token)


@router.get("/google")
async def google_login(request: Request):
    redirect_uri = f"{settings.BACKEND_URL}/api/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo or not userinfo.get("email"):
        raise HTTPException(status_code=400, detail="Could not retrieve email from Google")
    user = await find_or_create_google_user(
        db,
        email=userinfo["email"],
        google_id=userinfo["sub"],
    )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    active_client_id = await get_default_client_id(db, user.id, user.role)
    jwt_token = _issue_token(user, active_client_id)
    # Use URL fragment (#token=) so the JWT never reaches the server in logs or referrer headers.
    # SECURITY NOTE: URL fragments are readable by JavaScript executing on the page, so any
    # third-party script (analytics, ads, error tracking) loaded before the fragment is consumed
    # could exfiltrate the token. The proper fix is PKCE (RFC 7636): the frontend generates a
    # code_verifier, the backend stores a short-lived code and exchanges it for a token via a
    # POST request that never touches the URL. Until PKCE is implemented, minimize third-party
    # scripts on the /auth/callback page and consume the fragment immediately on load.
    return RedirectResponse(url=f"{settings.FRONTEND_URL}/auth/callback#token={jwt_token}")
