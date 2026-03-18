import logging

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.scoring_rule import ScoringRule
from app.schemas.scoring import ScoringRuleCreate, ScoringRuleUpdate

logger = logging.getLogger(__name__)

VALID_OPERATORS = {"contains", "equals", "greater_than", "less_than", "in_list", "not_empty"}

# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_rule(db: AsyncSession, data: ScoringRuleCreate, client_id: int) -> ScoringRule:
    rule = ScoringRule(client_id=client_id, **data.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def get_rule(db: AsyncSession, rule_id: int, client_id: int) -> ScoringRule | None:
    stmt = select(ScoringRule).where(ScoringRule.id == rule_id, ScoringRule.client_id == client_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_rules(db: AsyncSession, client_id: int) -> tuple[list[ScoringRule], int]:
    count_stmt = select(sa_func.count()).select_from(ScoringRule).where(ScoringRule.client_id == client_id)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = select(ScoringRule).where(ScoringRule.client_id == client_id).order_by(ScoringRule.id)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def update_rule(
    db: AsyncSession, rule_id: int, data: ScoringRuleUpdate, client_id: int
) -> ScoringRule | None:
    rule = await get_rule(db, rule_id, client_id)
    if rule is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(db: AsyncSession, rule_id: int, client_id: int) -> bool:
    rule = await get_rule(db, rule_id, client_id)
    if rule is None:
        return False
    await db.delete(rule)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------


def _resolve_field(lead: Lead, field_path: str):
    """Resolve a dotted field path against a lead, e.g. 'enrichment_data.apollo.company_size'."""
    parts = field_path.split(".")
    # First part is the lead attribute
    value = getattr(lead, parts[0], None)
    for part in parts[1:]:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _apply_operator(operator: str, field_value, rule_value: str) -> bool:
    if operator == "not_empty":
        return field_value is not None and str(field_value).strip() != ""

    if field_value is None:
        return False

    field_str = str(field_value)

    if operator == "contains":
        return rule_value.lower() in field_str.lower()
    elif operator == "equals":
        return field_str.lower() == rule_value.lower()
    elif operator == "greater_than":
        try:
            return float(field_str) > float(rule_value)
        except (ValueError, TypeError):
            return False
    elif operator == "less_than":
        try:
            return float(field_str) < float(rule_value)
        except (ValueError, TypeError):
            return False
    elif operator == "in_list":
        items = [item.strip().lower() for item in rule_value.split(",")]
        return field_str.lower() in items

    return False


def calculate_score(lead: Lead, rules: list) -> tuple[int, dict]:
    """Pure scoring function — no DB calls, no side effects.

    Returns (clamped_score, score_details_dict).
    Bad rules are skipped and logged; they never abort the whole calculation.
    """
    breakdown = []
    raw_total = 0

    for rule in rules:
        try:
            field_value = _resolve_field(lead, rule.field)
            matched = _apply_operator(rule.operator, field_value, rule.value)
        except Exception as exc:
            logger.warning(
                "Scoring rule %d (field=%s) raised an error — skipping",
                rule.id,
                rule.field,
                extra={"rule_id": rule.id, "error": str(exc)},
            )
            breakdown.append({
                "rule_id": rule.id,
                "field": rule.field,
                "operator": rule.operator,
                "value": rule.value,
                "points": rule.points,
                "matched": False,
                "error": str(exc),
            })
            continue

        breakdown.append({
            "rule_id": rule.id,
            "field": rule.field,
            "operator": rule.operator,
            "value": rule.value,
            "points": rule.points,
            "matched": matched,
        })

        if matched:
            raw_total += rule.points

    clamped = max(0, min(100, raw_total))
    score_details = {
        "rules": breakdown,
        "total_raw": raw_total,
        "total": clamped,
    }
    return clamped, score_details


async def score_lead(db: AsyncSession, lead: Lead, client_id: int) -> int:
    """Evaluate all active scoring rules against a lead. Updates lead.score and lead.score_details."""
    stmt = select(ScoringRule).where(
        ScoringRule.client_id == client_id,
        ScoringRule.is_active.is_(True),
    )
    result = await db.execute(stmt)
    rules = list(result.scalars().all())

    clamped, score_details = calculate_score(lead, rules)
    lead.score = clamped
    lead.score_details = score_details
    return clamped


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = {
    "b2b_saas": {
        "name": "B2B SaaS",
        "description": "Scoring rules optimized for B2B SaaS lead qualification",
        "rules": [
            {"field": "title", "operator": "contains", "value": "VP", "points": 20},
            {"field": "title", "operator": "contains", "value": "Director", "points": 15},
            {"field": "title", "operator": "contains", "value": "C-level", "points": 25},
            {"field": "title", "operator": "contains", "value": "Manager", "points": 10},
            {"field": "enrichment_data.apollo.company_size", "operator": "greater_than", "value": "50", "points": 15},
            {"field": "enrichment_data.apollo.company_size", "operator": "greater_than", "value": "200", "points": 10},
            {"field": "enrichment_data.apollo.industry", "operator": "equals", "value": "Technology", "points": 10},
            {"field": "source", "operator": "equals", "value": "website", "points": 5},
            {"field": "phone", "operator": "not_empty", "value": "_", "points": 5},
        ],
    },
}


def get_templates() -> list[dict]:
    return [
        {"name": key, "description": t["description"], "rules": t["rules"]}
        for key, t in TEMPLATES.items()
    ]


async def apply_template(db: AsyncSession, template_name: str, client_id: int) -> list[ScoringRule]:
    template = TEMPLATES.get(template_name)
    if template is None:
        return []

    created = []
    for rule_data in template["rules"]:
        rule = ScoringRule(client_id=client_id, is_active=True, **rule_data)
        db.add(rule)
        created.append(rule)

    await db.commit()
    for rule in created:
        await db.refresh(rule)

    return created
