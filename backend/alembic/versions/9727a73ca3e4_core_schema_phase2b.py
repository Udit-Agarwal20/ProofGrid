"""core_schema_phase2b

Revision ID: 9727a73ca3e4
Revises: 21242d5d8505
Create Date: 2026-09-27 02:31:11.880693

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9727a73ca3e4'
down_revision: Union[str, Sequence[str], None] = '21242d5d8505'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to Phase 2B corrected core model."""
    op.create_table(
        'projects',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_projects')),
        sa.UniqueConstraint('slug', name=op.f('uq_projects_slug')),
    )

    op.create_table(
        'entities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('canonical_name', sa.String(length=255), nullable=False),
        sa.Column('stable_entity_key', sa.String(length=255), nullable=True),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_entities_project_id_projects'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_entities')),
    )
    op.create_index('ix_entities_canonical_name', 'entities', ['canonical_name'], unique=False)
    op.create_index('ix_entities_project_type', 'entities', ['project_id', 'entity_type'], unique=False)
    op.create_index(
        'ux_entities_project_stable_key',
        'entities',
        ['project_id', 'stable_entity_key'],
        unique=True,
        postgresql_where=sa.text('stable_entity_key IS NOT NULL'),
    )

    op.create_table(
        'outbox_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('aggregate_type', sa.String(length=64), nullable=False),
        sa.Column('aggregate_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('available_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('PENDING', 'PROCESSING', 'PUBLISHED', 'FAILED', 'DEAD_LETTER')", name=op.f('ck_outbox_events_status')),
        sa.CheckConstraint('attempt_count >= 0', name=op.f('ck_outbox_events_attempt_count')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_outbox_events_project_id_projects'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_outbox_events')),
    )
    op.create_index('ix_outbox_events_project_id', 'outbox_events', ['project_id'], unique=False)
    op.create_index('ix_outbox_events_status_available', 'outbox_events', ['status', 'available_at'], unique=False)
    op.create_index('ix_outbox_events_aggregate', 'outbox_events', ['aggregate_type', 'aggregate_id'], unique=False)

    op.create_table(
        'requirements',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('original_prompt', sa.Text(), nullable=False),
        sa.Column('requirement_spec', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'COMPILED', 'ACCEPTED', 'REJECTED')", name=op.f('ck_requirements_status')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_requirements_project_id_projects'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_requirements')),
    )
    op.create_index('ix_requirements_project_id', 'requirements', ['project_id'], unique=False)

    op.create_table(
        'sources',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('canonical_url', sa.Text(), nullable=False),
        sa.Column('domain', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("source_type IN ('WEB_PAGE', 'API', 'RSS', 'DOCUMENT', 'FIXTURE')", name=op.f('ck_sources_source_type')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_sources_project_id_projects'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_sources')),
        sa.UniqueConstraint('project_id', 'canonical_url', name='uq_sources_project_canonical_url'),
    )
    op.create_index('ix_sources_project_domain', 'sources', ['project_id', 'domain'], unique=False)

    op.create_table(
        'dataset_schemas',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('requirement_id', sa.UUID(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('schema_definition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('version_number > 0', name=op.f('ck_dataset_schemas_version_number')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_dataset_schemas_project_id_projects'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['requirement_id'], ['requirements.id'], name=op.f('fk_dataset_schemas_requirement_id_requirements'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_dataset_schemas')),
        sa.UniqueConstraint('requirement_id', 'version_number', name='uq_dataset_schemas_requirement_version'),
    )
    op.create_index('ix_dataset_schemas_project_id', 'dataset_schemas', ['project_id'], unique=False)

    op.create_table(
        'entity_matches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('source_entity_id', sa.UUID(), nullable=False),
        sa.Column('target_entity_id', sa.UUID(), nullable=False),
        sa.Column('decision', sa.String(length=50), nullable=False),
        sa.Column('signals', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('score', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('reason', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('source_entity_id < target_entity_id', name=op.f('ck_entity_matches_canonical_pair_order')),
        sa.CheckConstraint("decision IN ('AUTO_MERGE', 'REVIEW', 'KEEP_SEPARATE', 'HUMAN_MERGE', 'HUMAN_SEPARATE')", name=op.f('ck_entity_matches_decision')),
        sa.CheckConstraint('score IS NULL OR (score >= 0.0 AND score <= 1.0)', name=op.f('ck_entity_matches_score')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_entity_matches_project_id_projects'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['source_entity_id'], ['entities.id'], name=op.f('fk_entity_matches_source_entity_id_entities'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['target_entity_id'], ['entities.id'], name=op.f('fk_entity_matches_target_entity_id_entities'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_entity_matches')),
        sa.UniqueConstraint('project_id', 'source_entity_id', 'target_entity_id', name='uq_entity_matches_pair'),
    )
    op.create_index('ix_entity_matches_source_entity', 'entity_matches', ['source_entity_id'], unique=False)
    op.create_index('ix_entity_matches_target_entity', 'entity_matches', ['target_entity_id'], unique=False)

    op.create_table(
        'workflows',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('requirement_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'ARCHIVED', 'PAUSED')", name=op.f('ck_workflows_status')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_workflows_project_id_projects'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['requirement_id'], ['requirements.id'], name=op.f('fk_workflows_requirement_id_requirements'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_workflows')),
    )
    op.create_index('ix_workflows_project_id', 'workflows', ['project_id'], unique=False)
    op.create_index('ix_workflows_requirement_id', 'workflows', ['requirement_id'], unique=False)

    op.create_table(
        'datasets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('workflow_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_datasets_project_id_projects'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], name=op.f('fk_datasets_workflow_id_workflows'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_datasets')),
        sa.UniqueConstraint('project_id', 'slug', name='uq_datasets_project_slug'),
    )
    op.create_index('ix_datasets_workflow_id', 'datasets', ['workflow_id'], unique=False)

    op.create_table(
        'trust_contracts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('requirement_id', sa.UUID(), nullable=False),
        sa.Column('dataset_schema_id', sa.UUID(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('contract_definition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('version_number > 0', name=op.f('ck_trust_contracts_version_number')),
        sa.ForeignKeyConstraint(['dataset_schema_id'], ['dataset_schemas.id'], name=op.f('fk_trust_contracts_dataset_schema_id_dataset_schemas'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_trust_contracts_project_id_projects'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['requirement_id'], ['requirements.id'], name=op.f('fk_trust_contracts_requirement_id_requirements'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_trust_contracts')),
        sa.UniqueConstraint('requirement_id', 'version_number', name='uq_trust_contracts_requirement_version'),
    )
    op.create_index('ix_trust_contracts_project_id', 'trust_contracts', ['project_id'], unique=False)
    op.create_index('ix_trust_contracts_dataset_schema_id', 'trust_contracts', ['dataset_schema_id'], unique=False)

    op.create_table(
        'workflow_versions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workflow_id', sa.UUID(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('dataset_schema_id', sa.UUID(), nullable=False),
        sa.Column('trust_contract_id', sa.UUID(), nullable=False),
        sa.Column('plan_dag', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('planner_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('version_number > 0', name=op.f('ck_workflow_versions_version_number')),
        sa.ForeignKeyConstraint(['dataset_schema_id'], ['dataset_schemas.id'], name=op.f('fk_workflow_versions_dataset_schema_id_dataset_schemas'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['trust_contract_id'], ['trust_contracts.id'], name=op.f('fk_workflow_versions_trust_contract_id_trust_contracts'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], name=op.f('fk_workflow_versions_workflow_id_workflows'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_versions')),
        sa.UniqueConstraint('workflow_id', 'version_number', name='uq_workflow_versions_workflow_version'),
    )
    op.create_index('ix_workflow_versions_dataset_schema_id', 'workflow_versions', ['dataset_schema_id'], unique=False)
    op.create_index('ix_workflow_versions_trust_contract_id', 'workflow_versions', ['trust_contract_id'], unique=False)

    op.create_table(
        'workflow_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('workflow_version_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('run_mode', sa.String(length=50), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('budget_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('error_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("run_mode IN ('LIVE', 'FIXTURE')", name=op.f('ck_workflow_runs_run_mode')),
        sa.CheckConstraint("status IN ('CREATED', 'QUEUED', 'RUNNING', 'PARTIAL', 'COMPLETED', 'FAILED', 'CANCEL_REQUESTED', 'CANCELLED')", name=op.f('ck_workflow_runs_status')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_workflow_runs_project_id_projects'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workflow_version_id'], ['workflow_versions.id'], name=op.f('fk_workflow_runs_workflow_version_id_workflow_versions'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_runs')),
    )
    op.create_index('ix_workflow_runs_project_id', 'workflow_runs', ['project_id'], unique=False)
    op.create_index('ix_workflow_runs_status', 'workflow_runs', ['status'], unique=False)
    op.create_index('ix_workflow_runs_version_status_created', 'workflow_runs', ['workflow_version_id', 'status', 'created_at'], unique=False)

    op.create_table(
        'dataset_versions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('dataset_id', sa.UUID(), nullable=False),
        sa.Column('dataset_schema_id', sa.UUID(), nullable=False),
        sa.Column('workflow_run_id', sa.UUID(), nullable=True),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('record_count', sa.Integer(), nullable=False),
        sa.Column('diff_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'FINALIZING', 'FINALIZED', 'FAILED')", name=op.f('ck_dataset_versions_status')),
        sa.CheckConstraint('record_count >= 0', name=op.f('ck_dataset_versions_record_count')),
        sa.CheckConstraint('version_number > 0', name=op.f('ck_dataset_versions_version_number')),
        sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], name=op.f('fk_dataset_versions_dataset_id_datasets'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['dataset_schema_id'], ['dataset_schemas.id'], name=op.f('fk_dataset_versions_dataset_schema_id_dataset_schemas'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_dataset_versions_project_id_projects'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workflow_run_id'], ['workflow_runs.id'], name=op.f('fk_dataset_versions_workflow_run_id_workflow_runs'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_dataset_versions')),
        sa.UniqueConstraint('dataset_id', 'version_number', name='uq_dataset_versions_dataset_version'),
    )
    op.create_index('ix_dataset_versions_project_id', 'dataset_versions', ['project_id'], unique=False)
    op.create_index('ix_dataset_versions_schema_id', 'dataset_versions', ['dataset_schema_id'], unique=False)
    op.create_index('ix_dataset_versions_run_id', 'dataset_versions', ['workflow_run_id'], unique=False)

    op.create_table(
        'raw_documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('workflow_run_id', sa.UUID(), nullable=True),
        sa.Column('source_id', sa.UUID(), nullable=False),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('final_url', sa.Text(), nullable=False),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('storage_uri', sa.String(length=1024), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('retrieval_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('size_bytes >= 0', name=op.f('ck_raw_documents_size_bytes')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_raw_documents_project_id_projects'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], name=op.f('fk_raw_documents_source_id_sources'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workflow_run_id'], ['workflow_runs.id'], name=op.f('fk_raw_documents_workflow_run_id_workflow_runs'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_raw_documents')),
    )
    op.create_index('ix_raw_documents_project_content_hash', 'raw_documents', ['project_id', 'content_hash'], unique=False)
    op.create_index('ix_raw_documents_source_id', 'raw_documents', ['source_id'], unique=False)
    op.create_index('ix_raw_documents_workflow_run_id', 'raw_documents', ['workflow_run_id'], unique=False)

    op.create_table(
        'step_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workflow_run_id', sa.UUID(), nullable=False),
        sa.Column('node_id', sa.String(length=64), nullable=False),
        sa.Column('operator_type', sa.String(length=64), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('input_hash', sa.String(length=64), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('available_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('worker_id', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("operator_type IN ('DISCOVER', 'FETCH_HTTP', 'FETCH_BROWSER', 'EXTRACT', 'NORMALIZE', 'VALIDATE', 'ENTITY_RESOLVE', 'RECONCILE', 'MATERIALIZE', 'INDEX', 'EXPORT')", name=op.f('ck_step_runs_operator_type')),
        sa.CheckConstraint("status IN ('PENDING', 'READY', 'LEASED', 'RUNNING', 'RETRY_WAIT', 'SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELLED')", name=op.f('ck_step_runs_status')),
        sa.CheckConstraint('attempt > 0', name=op.f('ck_step_runs_attempt')),
        sa.ForeignKeyConstraint(['workflow_run_id'], ['workflow_runs.id'], name=op.f('fk_step_runs_workflow_run_id_workflow_runs'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_step_runs')),
        sa.UniqueConstraint('workflow_run_id', 'node_id', 'attempt', name='ux_step_idempotency'),
    )
    op.create_index('ix_step_runs_ready', 'step_runs', ['status', 'available_at'], unique=False)
    op.create_index('ix_step_runs_run_status', 'step_runs', ['workflow_run_id', 'status'], unique=False)

    op.create_table(
        'workflow_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workflow_run_id', sa.UUID(), nullable=False),
        sa.Column('sequence_number', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('sequence_number >= 0', name=op.f('ck_workflow_events_sequence_number')),
        sa.ForeignKeyConstraint(['workflow_run_id'], ['workflow_runs.id'], name=op.f('fk_workflow_events_workflow_run_id_workflow_runs'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_events')),
        sa.UniqueConstraint('workflow_run_id', 'sequence_number', name='uq_workflow_events_run_sequence'),
    )

    op.create_table(
        'claims',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('workflow_run_id', sa.UUID(), nullable=False),
        sa.Column('raw_document_id', sa.UUID(), nullable=False),
        sa.Column('source_id', sa.UUID(), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=True),
        sa.Column('field_key', sa.String(length=64), nullable=False),
        sa.Column('raw_value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('normalized_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('extraction_method', sa.String(length=64), nullable=False),
        sa.Column('validation_flags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('claim_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], name=op.f('fk_claims_entity_id_entities'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_claims_project_id_projects'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['raw_document_id'], ['raw_documents.id'], name=op.f('fk_claims_raw_document_id_raw_documents'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], name=op.f('fk_claims_source_id_sources'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workflow_run_id'], ['workflow_runs.id'], name=op.f('fk_claims_workflow_run_id_workflow_runs'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_claims')),
    )
    op.create_index('ix_claims_project_id', 'claims', ['project_id'], unique=False)
    op.create_index('ix_claims_claim_hash', 'claims', ['claim_hash'], unique=False)
    op.create_index('ix_claims_entity_field', 'claims', ['entity_id', 'field_key'], unique=False)
    op.create_index('ix_claims_raw_document_id', 'claims', ['raw_document_id'], unique=False)
    op.create_index('ix_claims_source_id', 'claims', ['source_id'], unique=False)
    op.create_index('ix_claims_workflow_run_id', 'claims', ['workflow_run_id'], unique=False)

    op.create_table(
        'dataset_version_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('dataset_version_id', sa.UUID(), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('record_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('trust_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('record_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['dataset_version_id'], ['dataset_versions.id'], name=op.f('fk_dataset_version_records_dataset_version_id_dataset_versions'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], name=op.f('fk_dataset_version_records_entity_id_entities'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_dataset_version_records_project_id_projects'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_dataset_version_records')),
        sa.UniqueConstraint('dataset_version_id', 'entity_id', name='uq_dataset_version_records_version_entity'),
    )
    op.create_index('ix_dataset_version_records_project_id', 'dataset_version_records', ['project_id'], unique=False)
    op.create_index('ix_dataset_version_records_entity_id', 'dataset_version_records', ['entity_id'], unique=False)

    op.create_table(
        'canonical_values',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('dataset_version_id', sa.UUID(), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('field_key', sa.String(length=64), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('trust_status', sa.String(length=50), nullable=False),
        sa.Column('selected_claim_id', sa.UUID(), nullable=True),
        sa.Column('provenance_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("trust_status IN ('VERIFIED', 'SUPPORTED', 'SINGLE_SOURCE', 'CONFLICTING', 'NEEDS_REVIEW', 'MISSING')", name=op.f('ck_canonical_values_trust_status')),
        sa.ForeignKeyConstraint(['dataset_version_id'], ['dataset_versions.id'], name=op.f('fk_canonical_values_dataset_version_id_dataset_versions'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], name=op.f('fk_canonical_values_entity_id_entities'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_canonical_values_project_id_projects'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['selected_claim_id'], ['claims.id'], name=op.f('fk_canonical_values_selected_claim_id_claims'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_canonical_values')),
        sa.UniqueConstraint('dataset_version_id', 'entity_id', 'field_key', name='uq_canonical_values_version_entity_field'),
    )
    op.create_index('ix_canonical_values_project_id', 'canonical_values', ['project_id'], unique=False)
    op.create_index('ix_canonical_values_field_key', 'canonical_values', ['field_key'], unique=False)
    op.create_index('ix_canonical_values_selected_claim_id', 'canonical_values', ['selected_claim_id'], unique=False)

    op.create_table(
        'conflicts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('dataset_version_id', sa.UUID(), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('field_key', sa.String(length=64), nullable=False),
        sa.Column('conflict_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('resolved_claim_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("conflict_type IN ('VALUE_MISMATCH', 'SOURCE_CONTRADICTION', 'STALE_DATA', 'FORMAT_AMBIGUITY')", name=op.f('ck_conflicts_type')),
        sa.CheckConstraint("status IN ('OPEN', 'RESOLVED', 'DISMISSED')", name=op.f('ck_conflicts_status')),
        sa.ForeignKeyConstraint(['dataset_version_id'], ['dataset_versions.id'], name=op.f('fk_conflicts_dataset_version_id_dataset_versions'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], name=op.f('fk_conflicts_entity_id_entities'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_conflicts_project_id_projects'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['resolved_claim_id'], ['claims.id'], name=op.f('fk_conflicts_resolved_claim_id_claims'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_conflicts')),
        sa.UniqueConstraint('dataset_version_id', 'entity_id', 'field_key', name='uq_conflicts_version_entity_field'),
    )
    op.create_index('ix_conflicts_project_id', 'conflicts', ['project_id'], unique=False)
    op.create_index('ix_conflicts_status', 'conflicts', ['status'], unique=False)
    op.create_index('ix_conflicts_resolved_claim_id', 'conflicts', ['resolved_claim_id'], unique=False)

    op.create_table(
        'evidence_anchors',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('claim_id', sa.UUID(), nullable=False),
        sa.Column('raw_document_id', sa.UUID(), nullable=False),
        sa.Column('anchor_type', sa.String(length=64), nullable=False),
        sa.Column('locator', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('quoted_text', sa.Text(), nullable=True),
        sa.Column('normalized_text_hash', sa.String(length=64), nullable=True),
        sa.Column('verification_status', sa.String(length=50), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("anchor_type IN ('TEXT_SPAN', 'NORMALIZED_TEXT_SPAN', 'JSON_POINTER', 'DOM_SELECTOR', 'STRUCTURED_FIELD', 'API_RESPONSE_POINTER')", name=op.f('ck_evidence_anchors_type')),
        sa.CheckConstraint("verification_status IN ('UNVERIFIED', 'EXACT', 'NORMALIZED', 'JSON_POINTER', 'DOM_SELECTOR', 'UNANCHORED', 'VERIFIED', 'FAILED')", name=op.f('ck_evidence_anchors_status')),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], name=op.f('fk_evidence_anchors_claim_id_claims'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['raw_document_id'], ['raw_documents.id'], name=op.f('fk_evidence_anchors_raw_document_id_raw_documents'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence_anchors')),
    )
    op.create_index('ix_evidence_anchors_claim_id', 'evidence_anchors', ['claim_id'], unique=False)
    op.create_index('ix_evidence_anchors_raw_document_id', 'evidence_anchors', ['raw_document_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema from Phase 2B back to Phase 2A baseline."""
    op.drop_index('ix_evidence_anchors_raw_document_id', table_name='evidence_anchors')
    op.drop_index('ix_evidence_anchors_claim_id', table_name='evidence_anchors')
    op.drop_table('evidence_anchors')

    op.drop_index('ix_conflicts_resolved_claim_id', table_name='conflicts')
    op.drop_index('ix_conflicts_status', table_name='conflicts')
    op.drop_index('ix_conflicts_project_id', table_name='conflicts')
    op.drop_table('conflicts')

    op.drop_index('ix_canonical_values_selected_claim_id', table_name='canonical_values')
    op.drop_index('ix_canonical_values_field_key', table_name='canonical_values')
    op.drop_index('ix_canonical_values_project_id', table_name='canonical_values')
    op.drop_table('canonical_values')

    op.drop_index('ix_dataset_version_records_entity_id', table_name='dataset_version_records')
    op.drop_index('ix_dataset_version_records_project_id', table_name='dataset_version_records')
    op.drop_table('dataset_version_records')

    op.drop_index('ix_claims_workflow_run_id', table_name='claims')
    op.drop_index('ix_claims_source_id', table_name='claims')
    op.drop_index('ix_claims_raw_document_id', table_name='claims')
    op.drop_index('ix_claims_entity_field', table_name='claims')
    op.drop_index('ix_claims_claim_hash', table_name='claims')
    op.drop_index('ix_claims_project_id', table_name='claims')
    op.drop_table('claims')

    op.drop_table('workflow_events')

    op.drop_index('ix_step_runs_run_status', table_name='step_runs')
    op.drop_index('ix_step_runs_ready', table_name='step_runs')
    op.drop_table('step_runs')

    op.drop_index('ix_raw_documents_workflow_run_id', table_name='raw_documents')
    op.drop_index('ix_raw_documents_source_id', table_name='raw_documents')
    op.drop_index('ix_raw_documents_project_content_hash', table_name='raw_documents')
    op.drop_table('raw_documents')

    op.drop_index('ix_dataset_versions_run_id', table_name='dataset_versions')
    op.drop_index('ix_dataset_versions_schema_id', table_name='dataset_versions')
    op.drop_index('ix_dataset_versions_project_id', table_name='dataset_versions')
    op.drop_table('dataset_versions')

    op.drop_index('ix_workflow_runs_version_status_created', table_name='workflow_runs')
    op.drop_index('ix_workflow_runs_status', table_name='workflow_runs')
    op.drop_index('ix_workflow_runs_project_id', table_name='workflow_runs')
    op.drop_table('workflow_runs')

    op.drop_index('ix_workflow_versions_trust_contract_id', table_name='workflow_versions')
    op.drop_index('ix_workflow_versions_dataset_schema_id', table_name='workflow_versions')
    op.drop_table('workflow_versions')

    op.drop_index('ix_trust_contracts_dataset_schema_id', table_name='trust_contracts')
    op.drop_index('ix_trust_contracts_project_id', table_name='trust_contracts')
    op.drop_table('trust_contracts')

    op.drop_index('ix_datasets_workflow_id', table_name='datasets')
    op.drop_table('datasets')

    op.drop_index('ix_workflows_requirement_id', table_name='workflows')
    op.drop_index('ix_workflows_project_id', table_name='workflows')
    op.drop_table('workflows')

    op.drop_index('ix_entity_matches_target_entity', table_name='entity_matches')
    op.drop_index('ix_entity_matches_source_entity', table_name='entity_matches')
    op.drop_table('entity_matches')

    op.drop_index('ix_dataset_schemas_project_id', table_name='dataset_schemas')
    op.drop_table('dataset_schemas')

    op.drop_index('ix_sources_project_domain', table_name='sources')
    op.drop_table('sources')

    op.drop_index('ix_requirements_project_id', table_name='requirements')
    op.drop_table('requirements')

    op.drop_index('ix_outbox_events_aggregate', table_name='outbox_events')
    op.drop_index('ix_outbox_events_status_available', table_name='outbox_events')
    op.drop_index('ix_outbox_events_project_id', table_name='outbox_events')
    op.drop_table('outbox_events')

    op.drop_index('ux_entities_project_stable_key', table_name='entities', postgresql_where=sa.text('stable_entity_key IS NOT NULL'))
    op.drop_index('ix_entities_project_type', table_name='entities')
    op.drop_index('ix_entities_canonical_name', table_name='entities')
    op.drop_table('entities')

    op.drop_table('projects')
