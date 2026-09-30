"""Apply configured retention to unreferenced raw bodies and regeneratable exports."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.clock import utc_now  # noqa: E402
from app.persistence.queries.retention import retain_history  # noqa: E402


async def main() -> None:
    settings = get_settings()
    async with get_session_factory()() as session, session.begin():
        result = await retain_history(
            session,
            utc_now(),
            settings.RAW_RETENTION_DAYS,
            settings.EXPORT_RETENTION_DAYS,
            settings.DEMO_PROJECT_ID,
        )
        if "--apply" not in sys.argv:
            await session.rollback()
        print(json.dumps({**result, "applied": "--apply" in sys.argv}))


if __name__ == "__main__":
    asyncio.run(main())
