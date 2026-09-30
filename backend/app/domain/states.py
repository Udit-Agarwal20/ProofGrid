"""Authoritative transition functions for durable execution."""

from app.domain.enums import RunStatus, StepStatus

STEP_TRANSITIONS = {
    "PENDING": {"READY", "SKIPPED", "CANCELLED"},
    "READY": {"LEASED", "CANCELLED"},
    "LEASED": {"RUNNING", "RETRY_WAIT", "FAILED", "CANCELLED"},
    "RUNNING": {"SUCCEEDED", "RETRY_WAIT", "FAILED", "CANCELLED"},
    "RETRY_WAIT": {"READY", "CANCELLED"},
    "SUCCEEDED": set(),
    "FAILED": set(),
    "SKIPPED": set(),
    "CANCELLED": set(),
}
RUN_TRANSITIONS = {
    "CREATED": {"QUEUED"},
    "QUEUED": {"RUNNING", "CANCEL_REQUESTED", "FAILED"},
    "RUNNING": {"COMPLETED", "PARTIAL", "FAILED", "CANCEL_REQUESTED"},
    "CANCEL_REQUESTED": {"CANCELLED"},
    "COMPLETED": set(),
    "PARTIAL": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}
TERMINAL_RUNS = {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}


def transition_step(old: str, new: str) -> str:
    if new not in STEP_TRANSITIONS[old]:
        raise ValueError(f"Invalid step transition {old} -> {new}")
    return StepStatus(new).value


def transition_run(old: str, new: str) -> str:
    if new not in RUN_TRANSITIONS[old]:
        raise ValueError(f"Invalid run transition {old} -> {new}")
    return RunStatus(new).value
