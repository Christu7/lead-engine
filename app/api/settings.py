from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_id, get_current_active_user
from app.models.client import Client
from app.schemas.routing import (
    EnrichmentSettingsResponse,
    EnrichmentSettingsUpdate,
    RoutingSettingsResponse,
    RoutingSettingsUpdate,
)

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(get_current_active_user)],
)


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
    return EnrichmentSettingsResponse(**enrichment)


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
