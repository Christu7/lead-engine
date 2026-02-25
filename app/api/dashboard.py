from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_id, get_current_active_user
from app.schemas.dashboard import DashboardStatsResponse
from app.services.dashboard import get_dashboard_stats

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(get_current_active_user)],
)


@router.get("/stats", response_model=DashboardStatsResponse)
async def dashboard_stats(
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    return await get_dashboard_stats(db, client_id)
