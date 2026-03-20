from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class EnrichmentResult:
    provider_name: str
    success: bool
    data: dict = field(default_factory=dict)
    raw_response: dict | None = None
    error: str | None = None
    no_data: bool = False  # True when provider found no record (e.g. 404) — not a failure
    rate_limited: bool = False  # True when the provider returned HTTP 429


class EnrichmentProvider(ABC):
    # Subclasses must define provider_name as a class attribute, e.g.:
    #   provider_name = "apollo"
    provider_name: ClassVar[str]

    @abstractmethod
    def should_enrich(self, lead) -> bool: ...

    @abstractmethod
    async def enrich(self, lead, api_key: str) -> EnrichmentResult: ...
