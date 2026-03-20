from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_id, get_current_active_user, require_admin
from app.core.dynamic_config import dynamic_config
from app.core.exceptions import ConfigurationError
from app.models.client import Client
from app.schemas.routing import (
    EnrichmentSettingsResponse,
    EnrichmentSettingsUpdate,
    RoutingSettingsResponse,
    RoutingSettingsUpdate,
)
from app.services import api_key_store as store_svc

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(get_current_active_user)],
)

ALLOWED_KEY_NAMES = frozenset([
    "anthropic", "openai", "apollo",
    "ghl_inbound", "ghl_outbound",
    "clearbit", "proxycurl",
])
# Keys that are URLs, not API keys — skip automatic verification after save
_URL_KEYS = frozenset(["ghl_inbound", "ghl_outbound"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class KeyStatusResponse(BaseModel):
    key_name: str
    is_set: bool
    is_active: bool
    last_verified_at: datetime | None


class SetKeyRequest(BaseModel):
    value: str


class SetKeyResponse(BaseModel):
    key_name: str
    is_set: bool
    is_active: bool
    verified: bool
    last_verified_at: datetime | None


class VerifyKeyResponse(BaseModel):
    verified: bool
    last_verified_at: datetime | None


class AiProviderResponse(BaseModel):
    provider: str
    available: list[str]


class SetAiProviderRequest(BaseModel):
    provider: Literal["anthropic", "openai"]


def _mask_key(key: str | None) -> str | None:
    """Return key with all but the last 4 characters replaced by asterisks."""
    if not key:
        return key
    visible = key[-4:]
    return f"{'*' * max(len(key) - 4, 0)}{visible}"


@router.get("/routing", response_model=RoutingSettingsResponse)
async def get_routing_settings(
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    routing = (client.settings or {}).get("routing", {})
    return RoutingSettingsResponse(**routing)


@router.put("/routing", response_model=RoutingSettingsResponse)
async def update_routing_settings(
    data: RoutingSettingsUpdate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    settings = dict(client.settings or {})
    settings["routing"] = data.model_dump()
    client.settings = settings
    await db.commit()
    await db.refresh(client)
    return RoutingSettingsResponse(**client.settings["routing"])


@router.get("/enrichment", response_model=EnrichmentSettingsResponse)
async def get_enrichment_settings(
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    enrichment = (client.settings or {}).get("enrichment", {})

    # Merge with ApiKeyStore so the UI reflects globally-configured keys even when
    # the client has no per-client override. If a global key is configured but no
    # client-level key exists, show "****(global)" as the masked value.
    global_keys = {item["key_name"]: item for item in await store_svc.list_keys(db)}
    _PROVIDER_KEY_MAP = {
        "apollo_api_key": "apollo",
        "clearbit_api_key": "clearbit",
        "proxycurl_api_key": "proxycurl",
    }

    def _resolve(settings_field: str) -> str | None:
        client_val = enrichment.get(settings_field)
        if client_val:
            return _mask_key(client_val)
        store_name = _PROVIDER_KEY_MAP.get(settings_field)
        global_entry = global_keys.get(store_name) if store_name else None
        if global_entry and global_entry.get("is_set") and global_entry.get("is_active"):
            return "****(global)"
        return None

    return EnrichmentSettingsResponse(
        apollo_api_key=_resolve("apollo_api_key"),
        clearbit_api_key=_resolve("clearbit_api_key"),
        proxycurl_api_key=_resolve("proxycurl_api_key"),
    )


@router.put("/enrichment", response_model=EnrichmentSettingsResponse)
async def update_enrichment_settings(
    data: EnrichmentSettingsUpdate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    settings = dict(client.settings or {})
    existing = settings.get("enrichment", {})
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    existing.update(updates)
    settings["enrichment"] = existing
    client.settings = settings
    await db.commit()
    await db.refresh(client)
    return EnrichmentSettingsResponse(**client.settings["enrichment"])


# ── API Key Store endpoints (admin-only) ──────────────────────────────────────


@router.get("/keys", response_model=list[KeyStatusResponse], summary="List API key metadata")
async def list_keys(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> list[KeyStatusResponse]:
    """Return metadata for all stored API keys. Key values are never included."""
    stored = await store_svc.list_keys(db)
    stored_by_name = {item["key_name"]: item for item in stored}

    result: list[KeyStatusResponse] = []
    seen: set[str] = set()

    for name in sorted(ALLOWED_KEY_NAMES):
        item = stored_by_name.get(name)
        result.append(KeyStatusResponse(
            key_name=name,
            is_set=item["is_set"] if item else False,
            is_active=item["is_active"] if item else False,
            last_verified_at=item["last_verified_at"] if item else None,
        ))
        seen.add(name)

    # Include any unexpected stored keys not in the allowed set
    for item in stored:
        if item["key_name"] not in seen:
            result.append(KeyStatusResponse(
                key_name=item["key_name"],
                is_set=item["is_set"],
                is_active=item["is_active"],
                last_verified_at=item["last_verified_at"],
            ))
    return result


@router.put(
    "/keys/{key_name}",
    response_model=SetKeyResponse,
    summary="Set or update an API key",
)
async def set_key(
    key_name: str,
    body: SetKeyRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> SetKeyResponse:
    if key_name not in ALLOWED_KEY_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown key name '{key_name}'. Allowed: {sorted(ALLOWED_KEY_NAMES)}",
        )
    if not body.value or not body.value.strip():
        raise HTTPException(status_code=400, detail="Key value must not be empty")

    record = await store_svc.set_key(db, key_name, body.value.strip())

    # Auto-verify API keys immediately after save (not for URL-type keys)
    verified = False
    if key_name not in _URL_KEYS:
        verified = await store_svc.verify_key(db, key_name)
        # Re-fetch to get updated last_verified_at
        await db.refresh(record)

    return SetKeyResponse(
        key_name=record.key_name,
        is_set=record.key_value is not None,
        is_active=record.is_active,
        verified=verified,
        last_verified_at=record.last_verified_at,
    )


@router.delete("/keys/{key_name}", status_code=204, summary="Delete an API key")
async def delete_key(
    key_name: str,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> None:
    deleted = await store_svc.delete_key(db, key_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Key '{key_name}' not found")


@router.post(
    "/keys/{key_name}/verify",
    response_model=VerifyKeyResponse,
    summary="Verify an API key by making a test call",
)
async def verify_key(
    key_name: str,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> VerifyKeyResponse:
    if key_name not in ALLOWED_KEY_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown key name '{key_name}'. Allowed: {sorted(ALLOWED_KEY_NAMES)}",
        )
    ok = await store_svc.verify_key(db, key_name)

    # Fetch the current last_verified_at (updated by verify_key on success)
    stored = await store_svc.list_keys(db)
    last_verified = next(
        (item["last_verified_at"] for item in stored if item["key_name"] == key_name),
        None,
    )
    return VerifyKeyResponse(verified=ok, last_verified_at=last_verified)


# ── AI Provider endpoints (admin-only) ───────────────────────────────────────


@router.get("/ai-provider", response_model=AiProviderResponse, summary="Get active AI provider")
async def get_ai_provider(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> AiProviderResponse:
    """Returns the active provider and which providers have a key configured."""
    available: list[str] = []
    for provider_name in ("anthropic", "openai"):
        stored = await store_svc.list_keys(db)
        item = next((i for i in stored if i["key_name"] == provider_name), None)
        # Also check env var fallback
        try:
            await dynamic_config.get_key(db, provider_name)
            available.append(provider_name)
        except ConfigurationError:
            pass

    try:
        provider = await dynamic_config.get_ai_provider(db)
    except ConfigurationError:
        provider = "anthropic"  # default when nothing is configured

    return AiProviderResponse(provider=provider, available=available)


@router.put("/ai-provider", response_model=AiProviderResponse, summary="Set active AI provider")
async def set_ai_provider(
    body: SetAiProviderRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> AiProviderResponse:
    """Validate the chosen provider has a key, then store the preference."""
    # Validate the chosen provider has a key available
    try:
        await dynamic_config.get_key(db, body.provider)
    except ConfigurationError:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot set provider to '{body.provider}': no API key is configured for it. "
                   f"Set the key first via PUT /api/settings/keys/{body.provider}.",
        )

    # Store preference in ApiKeyStore (encrypted, consistent with other keys)
    await store_svc.set_key(db, "ai_provider_preference", body.provider)

    # Return updated state
    available: list[str] = []
    for provider_name in ("anthropic", "openai"):
        try:
            await dynamic_config.get_key(db, provider_name)
            available.append(provider_name)
        except ConfigurationError:
            pass

    return AiProviderResponse(provider=body.provider, available=available)
