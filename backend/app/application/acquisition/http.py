"""Public HTTP collection with DNS pinning, redirect checks, robots and bounded bodies."""

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.application.acquisition.models import AcquiredDocument
from app.application.acquisition.safety import registrable_domain, resolve_public
from app.core.errors import ProofGridError
from app.domain.clock import Clock, utc_now

USER_AGENT = "ProofGrid/1.0 (public business evidence collection)"
ACCEPTED = {
    "text/html",
    "application/json",
    "application/ld+json",
    "text/plain",
    "application/xml",
    "text/xml",
    "application/rss+xml",
    "application/atom+xml",
    "text/csv",
}
Resolver = Callable[[str], Awaitable[tuple[str, list[str]]]]


class SafeHttpAcquirer:
    def __init__(
        self,
        *,
        clock: Clock = utc_now,
        max_bytes: int = 5_000_000,
        global_limit: int = 8,
        domain_limit: int = 2,
        allowed_domains: list[str] | None = None,
        resolver: Resolver = resolve_public,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.clock = clock
        self.max_bytes = max_bytes
        self.allowed_domains = allowed_domains or []
        self.resolver = resolver
        self.transport = transport
        self.global_sem = asyncio.Semaphore(global_limit)
        self.domains: defaultdict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(domain_limit)
        )

    async def _request(self, url: str, *, obey_robots: bool = False) -> tuple[int, str, str, str]:
        for _ in range(6):
            url, ips = await self.resolver(url)
            p = urlsplit(url)
            host = p.hostname or ""
            if self.allowed_domains and host not in self.allowed_domains:
                raise ProofGridError(
                    "SOURCE_BLOCKED_BY_POLICY", "Source is outside the configured domain allowlist."
                )
            if obey_robots:
                await self._check_robots(url)
            # Connecting to the checked IP prevents a second DNS lookup/rebinding.
            pinned = httpx.URL(url).copy_with(host=ips[0])
            async with self.global_sem, self.domains[registrable_domain(host)]:  # noqa: SIM117
                async with httpx.AsyncClient(
                    transport=self.transport,
                    trust_env=False,
                    timeout=httpx.Timeout(12, connect=5),
                    follow_redirects=False,
                ) as client:
                    async with client.stream(
                        "GET",
                        pinned,
                        headers={
                            "Host": p.netloc,
                            "User-Agent": USER_AGENT,
                            "Accept": ", ".join(sorted(ACCEPTED)),
                        },
                        extensions={"sni_hostname": host},
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise ProofGridError(
                                    "SOURCE_REDIRECT_INVALID",
                                    "Source returned an invalid redirect.",
                                )
                            url = urljoin(url, location)
                            continue
                        if response.status_code == 429 or response.status_code >= 500:
                            raise ProofGridError(
                                "SOURCE_UNAVAILABLE",
                                "Source temporarily unavailable.",
                                retryable=True,
                            )
                        mime = response.headers.get("content-type", "").split(";")[0].lower()
                        if response.status_code == 200 and mime not in ACCEPTED:
                            raise ProofGridError(
                                "UNSUPPORTED_CONTENT_TYPE", "Source content type is not supported."
                            )
                        length = response.headers.get("content-length")
                        if length and (not length.isdigit() or int(length) > self.max_bytes):
                            raise ProofGridError(
                                "SOURCE_TOO_LARGE", "Source exceeds body size limit."
                            )
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self.max_bytes:
                                raise ProofGridError(
                                    "SOURCE_TOO_LARGE", "Source exceeds body size limit."
                                )
                        return (
                            response.status_code,
                            mime,
                            body.decode("utf-8", errors="replace"),
                            url,
                        )
        raise ProofGridError("SOURCE_REDIRECT_LIMIT", "Source exceeded redirect limit.")

    async def _check_robots(self, url: str) -> None:
        p = urlsplit(url)
        status, _, robots, _ = await self._request(f"{p.scheme}://{p.netloc}/robots.txt")
        if status == 200:
            parser = RobotFileParser()
            parser.parse(robots.splitlines())
            if not parser.can_fetch("ProofGrid", url):
                raise ProofGridError(
                    "SOURCE_ROBOTS_DISALLOW", "Source robots policy disallows collection."
                )
        elif status != 404:
            raise ProofGridError(
                "SOURCE_BLOCKED_BY_POLICY", "Source robots policy could not be confirmed."
            )

    async def fetch(self, url: str) -> AcquiredDocument:
        try:
            async with asyncio.timeout(40):
                status, mime, body, final_url = await self._request(url, obey_robots=True)
                if status != 200:
                    raise ProofGridError(
                        "SOURCE_REQUIRES_MANUAL_ACCESS",
                        "Source is unavailable for public collection.",
                    )
                if any(
                    marker in body.lower()
                    for marker in (
                        "g-recaptcha",
                        "cf-chl-",
                        "subscribe to continue",
                        "sign in to continue",
                    )
                ):
                    raise ProofGridError(
                        "SOURCE_REQUIRES_MANUAL_ACCESS", "Source requires manual access."
                    )
                return AcquiredDocument(
                    url=final_url,
                    content=body,
                    content_type=mime,
                    retrieved_at=self.clock(),
                    acquisition_method="API" if "json" in mime else "HTTP",
                    metadata={"robots_allowed": True, "parser_version": "1.0"},
                )
        except (httpx.HTTPError, TimeoutError):
            raise ProofGridError(
                "SOURCE_TIMEOUT", "Source request failed or timed out.", retryable=True
            ) from None
