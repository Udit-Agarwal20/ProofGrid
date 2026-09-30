"""Durable PostgreSQL workflow worker and outbox dispatcher."""

import argparse
import asyncio
import functools
import signal
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

# Ensure backend root is on sys.path when invoked directly as a script
_backend_root = str(Path(__file__).resolve().parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from app.application.execution.factory import create_dispatcher, create_runner  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.db.engine import dispose_async_engine  # noqa: E402


class ProofGridWorker:
    """Background consumer with bounded execution and graceful shutdown."""

    def __init__(self) -> None:
        self.settings = get_settings()
        configure_logging(service_name="proofgrid-worker", log_level=self.settings.LOG_LEVEL)
        self.logger = get_logger("proofgrid.worker")
        self.stop_event = asyncio.Event()

    def handle_signal(self, sig: int, frame: Any) -> None:
        """Handle termination signals gracefully."""
        self.logger.info(
            "Worker received termination signal",
            extra={"signal": signal.Signals(sig).name},
        )
        self.stop_event.set()

    async def run(self, run_once: bool = False) -> int:
        """Execute worker lifecycle."""
        self.logger.info(
            "ProofGrid Worker initialized successfully",
            extra={
                "service": "proofgrid-worker",
                "version": self.settings.APP_VERSION,
                "env": self.settings.APP_ENV,
                "status": "configured",
            },
        )

        if run_once:
            self.logger.info("Worker executed in --once mode. Exiting cleanly.")
            return 0

        # Register signal handlers in the asyncio event loop
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, functools.partial(self.handle_signal, sig, None))
            except NotImplementedError:
                # Windows fallback
                signal.signal(sig, self.handle_signal)

        self.logger.info("Worker polling the durable PostgreSQL queue...")

        runner = create_runner(self.settings)
        dispatcher = create_dispatcher(self.settings)
        try:
            while not self.stop_event.is_set():
                did_work = await runner.tick()
                did_work = await dispatcher.tick() or did_work
                if not did_work:
                    with suppress(TimeoutError):
                        await asyncio.wait_for(self.stop_event.wait(), timeout=0.5)
        finally:
            await dispose_async_engine()
        self.logger.info("ProofGrid Worker graceful shutdown complete.")
        return 0


def main() -> None:
    """CLI entrypoint for worker."""
    parser = argparse.ArgumentParser(description="ProofGrid Worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run startup and exit immediately (useful for health checks & tests)",
    )
    args = parser.parse_args()

    worker = ProofGridWorker()
    exit_code = asyncio.run(worker.run(run_once=args.once))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
