"""Discovery adapters do not acquire documents or confer source authority."""

from typing import Protocol

import httpx
from pydantic import SecretStr

from app.application.acquisition.models import SearchHit
from app.application.acquisition.safety import canonical_url
from app.core.errors import ProofGridError


class SearchProvider(Protocol):
    async def search(self, query: str, *, limit: int) -> list[SearchHit]: ...


class FixtureSearchProvider:
    def __init__(self, urls: list[str]):
        self.urls = urls

    async def search(self, query: str, *, limit: int) -> list[SearchHit]:
        return [SearchHit(url=url, title="Fixture evidence") for url in self.urls[:limit]]


class BraveSearchProvider:
    def __init__(self, key: SecretStr):
        self.key = key

    async def search(self, query: str, *, limit: int) -> list[SearchHit]:
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": min(limit, 20)},
                    headers={"X-Subscription-Token": self.key.get_secret_value()},
                )
                response.raise_for_status()
                hits = response.json().get("web", {}).get("results", [])
            output = []
            for hit in hits[:limit]:
                try:
                    output.append(
                        SearchHit(url=canonical_url(hit["url"]), title=hit.get("title", "")[:500])
                    )
                except (ProofGridError, KeyError):
                    continue
            return output
        except (httpx.HTTPError, ValueError, TypeError):
            raise ProofGridError(
                "SEARCH_UNAVAILABLE",
                "Search provider failed; explicit source hints can still be used.",
                retryable=True,
            ) from None


class UnconfiguredSearchProvider:
    async def search(self, query: str, *, limit: int) -> list[SearchHit]:
        raise ProofGridError(
            "SEARCH_NOT_CONFIGURED",
            "Configure Brave Search or supply explicit permitted source URLs.",
        )
