"""Core domain enumerations for ProofGrid.

Terminology and states strictly reflect the resolution in CONFLICT_REGISTER.md and DECISION_LOG.md.
"""

from enum import StrEnum


class OperatorType(StrEnum):
    """Allowed operator types for PlanDAG execution nodes."""

    DISCOVER = "DISCOVER"
    FETCH_HTTP = "FETCH_HTTP"
    FETCH_BROWSER = "FETCH_BROWSER"
    EXTRACT = "EXTRACT"
    NORMALIZE = "NORMALIZE"
    VALIDATE = "VALIDATE"
    ENTITY_RESOLVE = "ENTITY_RESOLVE"
    RECONCILE = "RECONCILE"
    MATERIALIZE = "MATERIALIZE"
    INDEX = "INDEX"
    EXPORT = "EXPORT"


class RunStatus(StrEnum):
    """Lifecycle states for a complete workflow run."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"


class StepStatus(StrEnum):
    """Execution states for an individual DAG step in the queue."""

    PENDING = "PENDING"
    READY = "READY"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class TrustStatus(StrEnum):
    """Categorical, rule-derived trust states for a canonical field."""

    VERIFIED = "VERIFIED"
    SUPPORTED = "SUPPORTED"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    CONFLICTING = "CONFLICTING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    MISSING = "MISSING"


class EvidenceStatus(StrEnum):
    """Verification resolution status for an evidence anchor."""

    EXACT = "EXACT"
    NORMALIZED = "NORMALIZED"
    JSON_POINTER = "JSON_POINTER"
    DOM_SELECTOR = "DOM_SELECTOR"
    UNANCHORED = "UNANCHORED"


class EvidenceType(StrEnum):
    """Supported anchor resolution mechanisms."""

    TEXT_SPAN = "TEXT_SPAN"
    NORMALIZED_TEXT_SPAN = "NORMALIZED_TEXT_SPAN"
    JSON_POINTER = "JSON_POINTER"
    DOM_SELECTOR = "DOM_SELECTOR"
    STRUCTURED_FIELD = "STRUCTURED_FIELD"
    API_RESPONSE_POINTER = "API_RESPONSE_POINTER"


class EntityDecision(StrEnum):
    """Resolution outcomes for candidate entity pairs."""

    AUTO_MERGE = "AUTO_MERGE"
    REVIEW = "REVIEW"
    KEEP_SEPARATE = "KEEP_SEPARATE"
    HUMAN_MERGE = "HUMAN_MERGE"
    HUMAN_SEPARATE = "HUMAN_SEPARATE"


class FieldDataType(StrEnum):
    """Supported typed data types for RequirementSpec fields."""

    TEXT = "text"
    URL = "url"
    MONEY = "money"
    DATE = "date"
    LOCATION = "location"
    ENTITY_REF = "entity_ref"
    ENTITY_LIST = "entity_list"
    NUMBER = "number"
    BOOLEAN = "boolean"


class FieldOrigin(StrEnum):
    """Provenance origin of a schema field specification."""

    USER = "user"
    AI_INFERRED = "ai_inferred"
