"""Unit tests for the ProofGrid Worker process."""

import pytest

from worker.main import ProofGridWorker


@pytest.mark.asyncio
async def test_worker_startup_and_run_once() -> None:
    """Verify worker initializes configuration, emits startup log, and exits cleanly with --once."""
    worker = ProofGridWorker()
    assert worker.settings.APP_NAME == "proofgrid-api"
    exit_code = await worker.run(run_once=True)
    assert exit_code == 0


@pytest.mark.asyncio
async def test_worker_signal_shutdown() -> None:
    """Verify worker cleanly sets stop_event on termination signal."""
    worker = ProofGridWorker()
    assert not worker.stop_event.is_set()

    # Simulate SIGTERM signal
    worker.handle_signal(15, None)
    assert worker.stop_event.is_set()
