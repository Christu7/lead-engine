from pydantic import BaseModel


class RoutingSettingsUpdate(BaseModel):
    ghl_inbound_webhook_url: str | None = None
    ghl_outbound_webhook_url: str | None = None
    score_inbound_threshold: int = 70
    score_outbound_threshold: int = 40


class RoutingSettingsResponse(BaseModel):
    ghl_inbound_webhook_url: str | None = None
    ghl_outbound_webhook_url: str | None = None
    score_inbound_threshold: int = 70
    score_outbound_threshold: int = 40


class RoutingResult(BaseModel):
    destination: str
    status: str
    response_code: int | None = None
    score: int | None = None


class DestinationStats(BaseModel):
    destination: str
    total: int
    success: int
    failed: int


class RoutingStatsResponse(BaseModel):
    total: int
    success: int
    failed: int
    success_rate: float
    by_destination: list[DestinationStats]
