"""Composition root shared by the worker executable and integration tests."""

from uuid import uuid4

from app.ai.factory import create_structured_generation_provider
from app.application.acquisition.http import SafeHttpAcquirer
from app.application.acquisition.search import (
    BraveSearchProvider,
    FixtureSearchProvider,
    SearchProvider,
    UnconfiguredSearchProvider,
)
from app.application.execution.operators import OperatorExecutor, WorkerRunner, fixture_documents
from app.application.extraction.service import Extractor
from app.core.config import Settings
from app.db.session import get_session_factory
from app.persistence.queries.outbox import OutboxDispatcher
from app.persistence.queries.queue import PostgresQueue


def create_runner(settings: Settings) -> WorkerRunner:
    queue = PostgresQueue(
        get_session_factory(), settings.DEMO_PROJECT_ID, lease_seconds=settings.LEASE_SECONDS
    )
    search: SearchProvider
    if settings.SEARCH_PROVIDER == "brave" and settings.SEARCH_API_KEY:
        search = BraveSearchProvider(settings.SEARCH_API_KEY)
    elif settings.ACQUISITION_MODE == "FIXTURE":
        search = FixtureSearchProvider(
            [d.url for d in fixture_documents(settings.FIXTURE_SET)]
            if settings.ACQUISITION_MODE == "FIXTURE"
            else []
        )
    else:
        search = UnconfiguredSearchProvider()
    extractor = Extractor(
        None
        if settings.AI_PROVIDER == "fixture"
        else create_structured_generation_provider(settings)
    )
    http = SafeHttpAcquirer(
        max_bytes=settings.MAX_RESPONSE_BYTES,
        global_limit=settings.MAX_HTTP_CONCURRENCY,
        domain_limit=settings.MAX_DOMAIN_CONCURRENCY,
        allowed_domains=settings.ALLOWED_SOURCE_DOMAINS,
    )
    return WorkerRunner(
        queue,
        OperatorExecutor(
            queue,
            http,
            search,
            extractor,
            first_party_domains=settings.FIRST_PARTY_DOMAINS,
            fixture_set=settings.FIXTURE_SET,
        ),
        f"worker-{uuid4()}",
    )


def create_dispatcher(settings: Settings) -> "OutboxDispatcher":
    from typing import Any
    from uuid import UUID

    from app.core.logging import get_logger

    async def recorded(event_id: UUID, payload: dict[str, Any]) -> None:
        # Core events have no remote side effect. Log only IDs; indexing consumers are optional.
        get_logger("proofgrid.outbox").info(
            "Dataset event dispatched", extra={"event_id": str(event_id)}
        )

    return OutboxDispatcher(
        get_session_factory(),
        settings.DEMO_PROJECT_ID,
        {"dataset.version_created": recorded, "requirement.compiled": recorded},
    )
