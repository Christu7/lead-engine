"""CRUD and verification operations for the ApiKeyStore.

Rules:
- key_value is always encrypted before storage; decrypted on read.
- NEVER log or return the actual key value.
- list_keys() returns metadata only (is_set, is_active, last_verified_at).
"""
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt, encrypt
from app.models.api_key_store import ApiKeyStore

logger = logging.getLogger(__name__)

# Keys that can't be meaningfully verified via an API call (they're URLs, not keys)
_SKIP_VERIFY = {"ghl_inbound", "ghl_outbound"}


async def get_key(db: AsyncSession, key_name: str) -> str | None:
    """Return the decrypted plaintext key value, or None if not found / inactive."""
    result = await db.execute(
        select(ApiKeyStore).where(ApiKeyStore.key_name == key_name)
    )
    record = result.scalar_one_or_none()
    if record is None or not record.is_active or record.key_value is None:
        return None
    try:
        return decrypt(record.key_value)
    except Exception:
        logger.error(
            "api_key_store: failed to decrypt key — may be encrypted with a different key",
            extra={"key_name": key_name},
        )
        return None


async def set_key(db: AsyncSession, key_name: str, value: str) -> ApiKeyStore:
    """Encrypt and upsert the key. Resets last_verified_at (key changed)."""
    encrypted = encrypt(value)

    result = await db.execute(
        select(ApiKeyStore).where(ApiKeyStore.key_name == key_name)
    )
    record = result.scalar_one_or_none()

    if record is None:
        record = ApiKeyStore(
            key_name=key_name,
            key_value=encrypted,
            is_active=True,
            last_verified_at=None,
        )
        db.add(record)
    else:
        record.key_value = encrypted
        record.is_active = True
        record.last_verified_at = None
        record.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(record)
    logger.info("api_key_store: key set", extra={"key_name": key_name})
    return record


async def delete_key(db: AsyncSession, key_name: str) -> bool:
    """Hard delete the key record. Returns True if it existed."""
    result = await db.execute(
        select(ApiKeyStore).where(ApiKeyStore.key_name == key_name)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return False
    await db.delete(record)
    await db.commit()
    logger.info("api_key_store: key deleted", extra={"key_name": key_name})
    return True


async def list_keys(db: AsyncSession) -> list[dict]:
    """Return metadata for all stored keys. Never returns actual key values."""
    result = await db.execute(select(ApiKeyStore).order_by(ApiKeyStore.key_name))
    records = result.scalars().all()
    return [
        {
            "key_name": r.key_name,
            "is_set": r.key_value is not None,
            "is_active": r.is_active,
            "last_verified_at": r.last_verified_at,
        }
        for r in records
    ]


async def verify_key(db: AsyncSession, key_name: str) -> bool:
    """Make a cheap test call to verify the key works. Updates last_verified_at on success.

    Returns True if the key is valid, False otherwise. Never raises.
    """
    if key_name in _SKIP_VERIFY:
        logger.info(
            "api_key_store: verify skipped (URL type)",
            extra={"key_name": key_name},
        )
        return True

    plaintext = await get_key(db, key_name)
    if plaintext is None:
        logger.warning(
            "api_key_store: verify called but key not set or inactive",
            extra={"key_name": key_name},
        )
        return False

    ok = await _verify_call(key_name, plaintext)

    if ok:
        result = await db.execute(
            select(ApiKeyStore).where(ApiKeyStore.key_name == key_name)
        )
        record = result.scalar_one_or_none()
        if record:
            record.last_verified_at = datetime.now(timezone.utc)
            record.updated_at = datetime.now(timezone.utc)
            await db.commit()
        logger.info("api_key_store: key verified", extra={"key_name": key_name})
    else:
        logger.warning("api_key_store: key verification failed", extra={"key_name": key_name})

    return ok


async def _verify_call(key_name: str, key_value: str) -> bool:
    """Make the provider-specific cheapest possible test call."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if key_name == "anthropic":
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": key_value, "anthropic-version": "2023-06-01"},
                )
                return resp.status_code == 200

            elif key_name == "openai":
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key_value}"},
                )
                return resp.status_code == 200

            elif key_name == "apollo":
                resp = await client.get(
                    "https://api.apollo.io/v1/auth/health",
                    headers={"x-api-key": key_value, "Content-Type": "application/json"},
                )
                # 200 = valid key; anything else = invalid
                return resp.status_code == 200

            elif key_name == "clearbit":
                # 404 = domain not found but key is valid; 401 = invalid key
                resp = await client.get(
                    "https://company.clearbit.com/v2/companies/find",
                    params={"domain": "example.com"},
                    headers={"Authorization": f"Bearer {key_value}"},
                )
                return resp.status_code in (200, 404)

            elif key_name == "proxycurl":
                # 400 = bad request but key is valid; 401 = invalid key
                resp = await client.get(
                    "https://nubela.co/proxycurl/api/v2/linkedin",
                    params={"url": "https://www.linkedin.com/in/test"},
                    headers={"Authorization": f"Bearer {key_value}"},
                )
                return resp.status_code in (200, 400, 404)

            else:
                logger.warning(
                    "api_key_store: no verify logic for key_name",
                    extra={"key_name": key_name},
                )
                return False
    except Exception as exc:
        logger.warning(
            "api_key_store: verify call failed",
            extra={"key_name": key_name, "error": str(exc)},
        )
        return False
