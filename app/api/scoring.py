from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_id, get_current_active_user, require_admin
from app.schemas.scoring import (
    ScoringRuleCreate,
    ScoringRuleListResponse,
    ScoringRuleResponse,
    ScoringRuleUpdate,
    ScoringTemplateResponse,
)
from app.services import scoring as scoring_service

router = APIRouter(
    prefix="/scoring-rules",
    tags=["scoring"],
    dependencies=[Depends(get_current_active_user), Depends(require_admin)],
)


@router.post("/", response_model=ScoringRuleResponse, status_code=201)
async def create_rule(
    data: ScoringRuleCreate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    return await scoring_service.create_rule(db, data, client_id)


@router.get("/", response_model=ScoringRuleListResponse)
async def list_rules(
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    items, total = await scoring_service.list_rules(db, client_id)
    return ScoringRuleListResponse(items=items, total=total)


@router.get("/templates", response_model=list[ScoringTemplateResponse])
async def list_templates():
    return scoring_service.get_templates()


@router.post("/templates/{name}/apply", response_model=list[ScoringRuleResponse])
async def apply_template(
    name: str,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    rules = await scoring_service.apply_template(db, name, client_id)
    if not rules:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    return rules


@router.get("/{rule_id}", response_model=ScoringRuleResponse)
async def get_rule(
    rule_id: int,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    rule = await scoring_service.get_rule(db, rule_id, client_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Scoring rule not found")
    return rule


@router.patch("/{rule_id}", response_model=ScoringRuleResponse)
async def update_rule(
    rule_id: int,
    data: ScoringRuleUpdate,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    rule = await scoring_service.update_rule(db, rule_id, data, client_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Scoring rule not found")
    return rule


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: int,
    client_id: int = Depends(get_client_id),
    db: AsyncSession = Depends(get_db),
):
    deleted = await scoring_service.delete_rule(db, rule_id, client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scoring rule not found")
