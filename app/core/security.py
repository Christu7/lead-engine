import ipaddress
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------

# Private / reserved ranges that must never be reachable via user-supplied URLs.
# Includes RFC1918, loopback, link-local, AWS instance-metadata range, and IPv6 equivalents.
_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),     # shared address space (RFC6598)
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),          # unique local IPv6
    ipaddress.ip_network("fe80::/10"),         # link-local IPv6
]

_BLOCKED_HOSTNAMES = frozenset(["localhost", "0.0.0.0"])


def _assert_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """Raise ValueError if the IP is in any private or reserved range."""
    for network in _BLOCKED_NETWORKS:
        if ip in network:
            raise ValueError(
                f"IP address {ip} falls within the private/reserved range {network} "
                "and is not permitted"
            )
    if ip.is_loopback:
        raise ValueError(f"IP address {ip} is a loopback address and is not permitted")
    if ip.is_link_local:
        raise ValueError(f"IP address {ip} is a link-local address and is not permitted")
    if ip.is_multicast:
        raise ValueError(f"IP address {ip} is a multicast address and is not permitted")


def validate_webhook_url(url: str) -> None:
    """Validate a user-supplied URL to prevent Server-Side Request Forgery (SSRF).

    Rules enforced:
    - Must start with https://
    - Hostname must not be localhost, 0.0.0.0, or any variation
    - Hostname must not be a bare private/loopback IP address
    - DNS resolution of the hostname must not return a private/reserved IP

    Raises:
        ValueError: with a descriptive message if any check fails.

    NOTE: This function performs a synchronous DNS lookup. Call via
    ``await asyncio.to_thread(validate_webhook_url, url)`` in async handlers.
    """
    if not url.startswith("https://"):
        raise ValueError("URL must use HTTPS (must start with https://)")

    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must contain a valid hostname")

    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Hostname '{hostname}' is not permitted")

    # If the caller supplied a bare IP address, check it directly (no DNS needed).
    try:
        ip_addr = ipaddress.ip_address(hostname)
        _assert_public_ip(ip_addr)
        return
    except ValueError as exc:
        # Re-raise our SSRF error; swallow "not a valid IP address" ValueError.
        if "not permitted" in str(exc) or "private" in str(exc) or "loopback" in str(exc):
            raise
    # hostname is a domain name — resolve it and inspect each returned address.
    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve hostname '{hostname}': {exc}") from exc

    if not resolved:
        raise ValueError(f"Hostname '{hostname}' did not resolve to any IP address")

    for _family, _type, _proto, _canonname, sockaddr in resolved:
        addr_str = sockaddr[0]
        try:
            ip_addr = ipaddress.ip_address(addr_str)
            _assert_public_ip(ip_addr)
        except ValueError as exc:
            raise ValueError(
                f"URL hostname '{hostname}' resolves to a private/reserved address "
                f"({addr_str}) and is not permitted"
            ) from exc


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


@dataclass
class TokenData:
    user_id: int
    email: str
    role: str
    active_client_id: int | None
    token_version: int = field(default=1)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: int,
    email: str,
    role: str,
    active_client_id: int | None,
    token_version: int = 1,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": email,
        "user_id": user_id,
        "role": role,
        "active_client_id": active_client_id,
        "token_version": token_version,
        "iat": now,
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
            token_version=payload.get("token_version", 1),
        )
    except JWTError:
        return None
