"""Durable execution, bounded evidence and idempotency.

Revision ID: b73a8d401e20
Revises: 9727a73ca3e4
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b73a8d401e20"
down_revision = "9727a73ca3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "step_runs", sa.Column("priority", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "step_runs", sa.Column("output", postgresql.JSONB(), nullable=False, server_default="{}")
    )
    op.add_column("step_runs", sa.Column("error_code", sa.String(100), nullable=True))
    op.add_column("raw_documents", sa.Column("content", sa.Text(), nullable=True))
    op.add_column(
        "requirements",
        sa.Column("compiler_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_unique_constraint(
        "uq_step_runs_run_node", "step_runs", ["workflow_run_id", "node_id"]
    )
    op.create_unique_constraint(
        "uq_raw_document_observation",
        "raw_documents",
        ["workflow_run_id", "source_id", "content_hash"],
    )
    op.create_unique_constraint("uq_claims_run_hash", "claims", ["workflow_run_id", "claim_hash"])
    op.create_unique_constraint("uq_dataset_versions_run", "dataset_versions", ["workflow_run_id"])
    op.create_index(
        "ix_step_lease_expiry",
        "step_runs",
        ["lease_expires_at"],
        postgresql_where=sa.text("status IN ('LEASED', 'RUNNING')"),
    )
    op.create_index(
        "ix_records_data_gin", "dataset_version_records", ["record_data"], postgresql_using="gin"
    )
    op.create_table(
        "exports",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "dataset_version_id",
            sa.UUID(),
            sa.ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_id", "dataset_version_id", "format", name="uq_exports_version_format"
        ),
    )
    op.execute(
        """CREATE FUNCTION proofgrid_claim_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'claims are append-only'; END; $$"""
    )
    op.execute(
        "CREATE TRIGGER claims_append_only BEFORE UPDATE OR DELETE ON claims FOR EACH ROW EXECUTE FUNCTION proofgrid_claim_immutable()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER claims_append_only ON claims")
    op.execute("DROP FUNCTION proofgrid_claim_immutable()")
    op.drop_table("exports")
    op.drop_index("ix_records_data_gin", table_name="dataset_version_records")
    op.drop_index("ix_step_lease_expiry", table_name="step_runs")
    for table, name in [
        ("dataset_versions", "uq_dataset_versions_run"),
        ("claims", "uq_claims_run_hash"),
        ("raw_documents", "uq_raw_document_observation"),
        ("step_runs", "uq_step_runs_run_node"),
    ]:
        op.drop_constraint(name, table, type_="unique")
    op.drop_column("requirements", "compiler_metadata")
    op.drop_column("raw_documents", "content")
    for column in ["error_code", "output", "priority"]:
        op.drop_column("step_runs", column)
