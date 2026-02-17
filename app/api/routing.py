from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_id, get_current_active_user
from app.schemas.routing import RoutingStatsResponse
from app.services.routing import get_routing_stats

router = APIRouter(
    prefix="/routing",
    tags=["routing"],
    dependencies=[Depends(get_current_active_user)],
)


@router.get("/stats", response_model=RoutingStatsResponse)
async def routing_stats(
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    return await get_routing_stats(db, client_id)
