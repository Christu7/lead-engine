from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_id, get_current_active_user
from app.models.client import Client
from app.schemas.routing import RoutingSettingsResponse, RoutingSettingsUpdate

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
