import httpx

from app.core.exceptions import EnrichmentProviderError
from app.services.enrichment.base import EnrichmentProvider, EnrichmentResult


class ProxycurlProvider(EnrichmentProvider):
    provider_name = "proxycurl"

    def should_enrich(self, lead) -> bool:
        enrichment = lead.enrichment_data or {}
        # Requires linkedin_url, typically obtained from Apollo
        apollo_data = enrichment.get("apollo", {})
        linkedin_url = apollo_data.get("linkedin_url")
        if not linkedin_url:
            return False
        return "proxycurl" not in enrichment

    async def enrich(self, lead, api_key: str) -> EnrichmentResult:
        linkedin_url = (lead.enrichment_data or {}).get("apollo", {}).get("linkedin_url")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://nubela.co/proxycurl/api/v2/linkedin",
                    params={"url": linkedin_url},
                    headers={"Authorization": f"Bearer {api_key}"},
                )

                if resp.status_code == 404:
                    return EnrichmentResult(
                        provider_name=self.provider_name,
                        success=True,
                        data={},
                        raw_response=None,
                        no_data=True,
                    )

                resp.raise_for_status()
                body = resp.json()

            experiences = body.get("experiences") or []
            education = body.get("education") or []

            data = {
                "headline": body.get("headline"),
                "summary": body.get("summary"),
                "experiences": experiences[:5],
                "education": education[:3],
            }
            data = {k: v for k, v in data.items() if v is not None}

            return EnrichmentResult(
                provider_name=self.provider_name,
                success=True,
                data=data,
                raw_response=body,
            )
        except httpx.HTTPError as exc:
            raise EnrichmentProviderError(
                provider=self.provider_name,
                lead_id=lead.id,
                reason=str(exc),
                cause=exc,
            ) from exc
