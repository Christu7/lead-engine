from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_api_key_auth
from app.schemas.lead import LeadCreate, LeadResponse
from app.services import lead as lead_service

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
    dependencies=[Depends(get_api_key_auth)],
)


@router.post("/leads", response_model=LeadResponse, status_code=201)
async def create_lead_webhook(data: LeadCreate, db: AsyncSession = Depends(get_db)):
    lead = await lead_service.create_lead(db, data)
    return lead
