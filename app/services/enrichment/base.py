from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class EnrichmentResult:
    provider_name: str
    success: bool
    data: dict = field(default_factory=dict)
    raw_response: dict | None = None
    error: str | None = None


class EnrichmentProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def should_enrich(self, lead) -> bool: ...

    @abstractmethod
    async def enrich(self, lead, api_key: str) -> EnrichmentResult: ...
