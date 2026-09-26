"""Safe database schema introspection tool for developer inspection.

Verifies table inventory, migration head, and constraint presence on Neon.
NEVER prints credentials, passwords, or connection URLs.
"""

import asyncio
import sys

from sqlalchemy import inspect, text

from app.core.config import get_settings
from app.db.engine import create_engine_instance

EXPECTED_TABLES = {
    "projects",
    "requirements",
    "dataset_schemas",
    "trust_contracts",
    "workflows",
    "workflow_versions",
    "workflow_runs",
    "step_runs",
    "workflow_events",
    "sources",
    "raw_documents",
    "claims",
    "evidence_anchors",
    "entities",
    "entity_matches",
    "canonical_values",
    "conflicts",
    "datasets",
    "dataset_versions",
    "dataset_version_records",
    "outbox_events",
    "alembic_version",
}


async def main() -> int:
    settings = get_settings()
    if not settings.DATABASE_URL:
        print("[ERROR] DATABASE_URL is not configured.")
        return 1

    print("=" * 60)
    print("ProofGrid Schema Introspection (Safe / Sanitized)")
    print("=" * 60)
    print("Provider: PostgreSQL / Neon")

    engine = create_engine_instance()
    try:
        async with engine.connect() as conn:
            print("Database connectivity: OK")
            # 1. Check Alembic revision
            res = await conn.execute(text("SELECT version_num FROM alembic_version"))
            row = res.fetchone()
            version_num = row[0] if row else "<none>"
            print(f"Alembic Current Revision: {version_num}")

            # 2. Check table inventory
            res = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                    "ORDER BY table_name"
                )
            )
            tables = [r[0] for r in res.fetchall()]
            print(f"\nPublic Tables ({len(tables)} total):")
            for t in tables:
                status = "✓" if t in EXPECTED_TABLES else "?"
                print(f"  [{status}] {t}")

            table_set = set(tables)
            missing = EXPECTED_TABLES - table_set
            unexpected = table_set - EXPECTED_TABLES

            if missing:
                print(f"\n[FAIL] Missing expected tables: {missing}")
                return 1
            if unexpected:
                print(f"\n[FAIL] Unexpected tables found: {unexpected}")
                return 1

            # 3. Constraint summary via single fast catalog query
            res = await conn.execute(
                text(
                    "SELECT constraint_type, count(*) "
                    "FROM information_schema.table_constraints "
                    "WHERE table_schema = 'public' "
                    "GROUP BY constraint_type"
                )
            )
            constraint_counts = dict(res.fetchall())
            fk_count = constraint_counts.get("FOREIGN KEY", 0)
            uq_count = constraint_counts.get("UNIQUE", 0)
            ck_count = constraint_counts.get("CHECK", 0)
            pk_count = constraint_counts.get("PRIMARY KEY", 0)

            res = await conn.execute(
                text("SELECT count(*) FROM pg_indexes WHERE schemaname = 'public'")
            )
            idx_count = res.scalar() or 0

            print("\nConstraint & Index Inventory across public schema:")
            print(f"  Primary Keys:       {pk_count}")
            print(f"  Foreign Keys:       {fk_count}")
            print(f"  Unique Constraints: {uq_count}")
            print(f"  Check Constraints:  {ck_count}")
            print(f"  Indexes:            {idx_count}")

            print("\n[SUCCESS] Schema verification passed cleanly against live database.")
            return 0
    except Exception as e:
        print(f"\n[ERROR] Introspection failed: {type(e).__name__}: {e}")
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
