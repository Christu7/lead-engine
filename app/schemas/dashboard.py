from pydantic import BaseModel

from app.schemas.routing import DestinationStats


class LeadsBySource(BaseModel):
    source: str
    count: int


class ScoreBucket(BaseModel):
    label: str
    count: int


class ActivityItem(BaseModel):
    type: str
    lead_id: int
    lead_name: str
    description: str
    timestamp: str


class DashboardStatsResponse(BaseModel):
    total_leads: int
    leads_this_week: int
    leads_this_month: int
    enrichment_success_rate: float
    average_score: float | None
    leads_by_source: list[LeadsBySource]
    score_distribution: list[ScoreBucket]
    routing_breakdown: list[DestinationStats]
    recent_activity: list[ActivityItem]
