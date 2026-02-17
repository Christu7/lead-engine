import httpx

from app.services.enrichment.base import EnrichmentProvider, EnrichmentResult


class ApolloProvider(EnrichmentProvider):
    provider_name = "apollo"

    def should_enrich(self, lead) -> bool:
        if not lead.email:
            return False
        enrichment = lead.enrichment_data or {}
        return "apollo" not in enrichment

    async def enrich(self, lead, api_key: str) -> EnrichmentResult:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.apollo.io/api/v1/people/match",
                    headers={"x-api-key": api_key, "Content-Type": "application/json"},
                    json={"email": lead.email},
                )

                if resp.status_code == 404:
                    return EnrichmentResult(
                        provider_name=self.provider_name,
                        success=True,
                        data={},
                        raw_response=None,
                    )

                resp.raise_for_status()
                body = resp.json()

            person = body.get("person") or {}
            org = person.get("organization") or {}

            data = {
                "title": person.get("title"),
                "linkedin_url": person.get("linkedin_url"),
                "company_name": org.get("name"),
                "company_domain": org.get("primary_domain"),
                "company_industry": org.get("industry"),
                "employee_count": org.get("estimated_num_employees"),
                "city": person.get("city"),
                "state": person.get("state"),
                "country": person.get("country"),
            }
            # Remove None values
            data = {k: v for k, v in data.items() if v is not None}

            return EnrichmentResult(
                provider_name=self.provider_name,
                success=True,
                data=data,
                raw_response=body,
            )
        except httpx.HTTPError as e:
            return EnrichmentResult(
                provider_name=self.provider_name,
                success=False,
                error=str(e),
            )
