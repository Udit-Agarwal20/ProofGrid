"""ProofGrid authoritative database models.

All 21 core business models mapped to the SQLAlchemy 2.0 Base metadata.
"""

from app.db.models.dataset import (
    CanonicalValue,
    Conflict,
    Dataset,
    DatasetVersion,
    DatasetVersionRecord,
)
from app.db.models.entity import Entity, EntityMatch
from app.db.models.evidence import Claim, EvidenceAnchor, RawDocument, Source
from app.db.models.outbox import OutboxEvent
from app.db.models.project import Project
from app.db.models.requirement import DatasetSchema, Requirement, TrustContract
from app.db.models.workflow import (
    StepRun,
    Workflow,
    WorkflowEvent,
    WorkflowRun,
    WorkflowVersion,
)

__all__ = [
    # 1. Project
    "Project",
    # 2-4. Requirements, Schemas & Contracts
    "Requirement",
    "DatasetSchema",
    "TrustContract",
    # 5-9. Workflows, Execution & Events
    "Workflow",
    "WorkflowVersion",
    "WorkflowRun",
    "StepRun",
    "WorkflowEvent",
    # 10-13. Sources, Raw Evidence & Claims
    "Source",
    "RawDocument",
    "Claim",
    "EvidenceAnchor",
    # 14-15. Entities & Resolution
    "Entity",
    "EntityMatch",
    # 16-20. Datasets, Versioning, Canonical Values & Read Model
    "Dataset",
    "DatasetVersion",
    "CanonicalValue",
    "Conflict",
    "DatasetVersionRecord",
    # 21. Transactional Outbox
    "OutboxEvent",
]

from app.db.models.export import Export as Export
