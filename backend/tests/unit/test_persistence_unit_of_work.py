"""Offline unit tests for ProofGrid Persistence Application Layer.

Tests:
1. Unit of Work lifecycle and session sharing invariant across all 8 repositories.
2. Error handling, automatic rollback on exception, and automatic rollback if uncommitted.
3. No-hidden-commit invariant (repositories never independently commit or rollback).
4. Entity match canonical pair ordering and self-match rejection.
5. Append-only repository constraints (no generic update APIs).
6. Strict domain independence from SQLAlchemy and persistence modules.
7. Database error sanitization preventing credential and DSN leaks.
"""

from __future__ import annotations

import ast
import inspect
import os
import uuid
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

import app.persistence.repositories as repo_pkg
from app.persistence.errors import (
    PersistenceConflictError,
    PersistenceError,
    PersistenceIntegrityError,
    sanitize_error_message,
    translate_db_error,
)
from app.persistence.repositories.entity import EntityRepository
from app.persistence.repositories.outbox import OutboxEventCreate
from app.persistence.unit_of_work import SqlAlchemyUnitOfWork


@pytest.mark.asyncio
async def test_uow_shared_session_invariant() -> None:
    """Verify all 8 repositories in a UnitOfWork share the EXACT same AsyncSession."""
    mock_session = AsyncMock()
    mock_session.begin = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session_factory = MagicMock(return_value=mock_session)

    uow = SqlAlchemyUnitOfWork(session_factory=mock_session_factory)
    async with uow:
        # Assert active session is the one returned by factory
        assert uow.session is mock_session

        # Assert every single repository shares this exact session instance
        assert uow.projects.session is mock_session
        assert uow.requirements.session is mock_session
        assert uow.workflows.session is mock_session
        assert uow.sources.session is mock_session
        assert uow.claims.session is mock_session
        assert uow.entities.session is mock_session
        assert uow.datasets.session is mock_session
        assert uow.outbox.session is mock_session

    mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_uow_access_before_enter_raises() -> None:
    """Verify accessing repositories before entering UnitOfWork raises PersistenceError."""
    uow = SqlAlchemyUnitOfWork(session_factory=MagicMock())
    with pytest.raises(PersistenceError, match="must be entered"):
        _ = uow.projects

    with pytest.raises(PersistenceError, match="not active"):
        _ = uow.session


@pytest.mark.asyncio
async def test_uow_commit_calls_session_commit() -> None:
    """Verify explicit uow.commit() invokes session.commit() exactly once."""
    mock_session = AsyncMock()
    mock_session.begin = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session_factory = MagicMock(return_value=mock_session)

    uow = SqlAlchemyUnitOfWork(session_factory=mock_session_factory)
    async with uow:
        await uow.commit()

    mock_session.commit.assert_awaited_once()
    mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_uow_commit_twice_raises() -> None:
    """Verify calling uow.commit() a second time raises PersistenceError."""
    mock_session = AsyncMock()
    mock_session.begin = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.close = AsyncMock()

    uow = SqlAlchemyUnitOfWork(session_factory=MagicMock(return_value=mock_session))
    async with uow:
        await uow.commit()
        with pytest.raises(PersistenceError, match="already been committed"):
            await uow.commit()


@pytest.mark.asyncio
async def test_uow_auto_rollback_on_unhandled_exception() -> None:
    """Verify an unhandled exception inside with-block triggers automatic rollback."""
    mock_session = AsyncMock()
    mock_session.begin = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    uow = SqlAlchemyUnitOfWork(session_factory=MagicMock(return_value=mock_session))
    with pytest.raises(ValueError, match="simulated failure"):
        async with uow:
            raise ValueError("simulated failure")

    mock_session.rollback.assert_awaited_once()
    mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_uow_auto_rollback_when_exit_without_commit() -> None:
    """Verify exiting with-block without calling commit() triggers automatic rollback."""
    mock_session = AsyncMock()
    mock_session.begin = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    uow = SqlAlchemyUnitOfWork(session_factory=MagicMock(return_value=mock_session))
    async with uow:
        # Operations performed, but caller forgot/chose not to call await uow.commit()
        pass

    # Must have rolled back uncommitted work
    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_awaited_once()
    mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_uow_cannot_be_reused_after_close() -> None:
    """Verify a UnitOfWork instance cannot be entered or reused after closing."""
    mock_session = AsyncMock()
    mock_session.begin = AsyncMock()
    mock_session.close = AsyncMock()

    uow = SqlAlchemyUnitOfWork(session_factory=MagicMock(return_value=mock_session))
    async with uow:
        await uow.commit()

    with pytest.raises(PersistenceError, match="Cannot reuse a closed UnitOfWork"):
        async with uow:
            pass


def test_error_sanitization_masks_credentials() -> None:
    """Verify sensitive connection parameters and passwords are scrubbed from error strings."""
    leaked_dsn = "postgresql://user:super_secret_password@ep-cool-db.aws.neon.tech:5432/dbname"
    sanitized = sanitize_error_message(f"Connection failed: {leaked_dsn}")
    assert "super_secret_password" not in sanitized
    assert "user:***@" in sanitized

    pw_string = "Authentication failed with password=my_plaintext_pass and timeout"
    sanitized_pw = sanitize_error_message(pw_string)
    assert "my_plaintext_pass" not in sanitized_pw
    assert "password=***" in sanitized_pw


def test_translate_integrity_error_categorization() -> None:
    """Verify SQLAlchemy IntegrityErrors are categorized without leaking raw database strings."""
    # 1. Unique constraint
    uq_err = IntegrityError(
        statement="INSERT INTO projects ...",
        params={},
        orig=Exception('duplicate key value violates unique constraint "uq_projects_slug"'),
    )
    translated_uq = translate_db_error(uq_err)
    assert isinstance(translated_uq, PersistenceConflictError)
    assert translated_uq.conflict_key == "uq_projects_slug"

    # 2. Foreign key constraint
    fk_err = IntegrityError(
        statement="INSERT INTO requirements ...",
        params={},
        orig=Exception('insert violates foreign key constraint "fk_requirements_project_id"'),
    )
    translated_fk = translate_db_error(fk_err)
    assert isinstance(translated_fk, PersistenceIntegrityError)
    assert translated_fk.constraint_name == "fk_requirements_project_id"

    # 3. Check constraint
    ck_err = IntegrityError(
        statement="INSERT INTO requirements ...",
        params={},
        orig=Exception('violates check constraint "ck_requirements_status"'),
    )
    translated_ck = translate_db_error(ck_err)
    assert isinstance(translated_ck, PersistenceIntegrityError)
    assert translated_ck.constraint_name == "ck_requirements_status"


def test_entity_pair_canonicalization_order() -> None:
    """Verify EntityRepository normalizes entity pairs into canonical order (source < target)."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = EntityRepository(mock_session)

    id_smaller = uuid.UUID("11111111-1111-1111-1111-111111111111")
    id_larger = uuid.UUID("99999999-9999-9999-9999-999999999999")
    proj_id = uuid.uuid4()

    # Pass in inverted order (larger first)
    match = repo.add_entity_match(
        project_id=proj_id,
        entity_a_id=id_larger,
        entity_b_id=id_smaller,
        decision="AUTO_MERGE",
    )
    # Must be normalized into source < target
    assert match.source_entity_id == id_smaller
    assert match.target_entity_id == id_larger

    # Self-match must be rejected immediately at the repository boundary
    with pytest.raises(PersistenceIntegrityError, match="between an entity and itself"):
        repo.add_entity_match(
            project_id=proj_id,
            entity_a_id=id_smaller,
            entity_b_id=id_smaller,
            decision="AUTO_MERGE",
        )


def test_repositories_never_commit_or_rollback_independently() -> None:
    """Verify via AST analysis that no repository method invokes session.commit() or rollback()."""
    repo_dir = os.path.dirname(repo_pkg.__file__)
    for filename in os.listdir(repo_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            filepath = os.path.join(repo_dir, filename)
            with open(filepath) as f:
                tree = ast.parse(f.read(), filename=filename)

            for node in ast.walk(tree):
                # Check method calls like self._session.commit()
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in ("commit", "rollback"), (
                        f"Repository file {filename} at line {node.lineno} calls '{node.func.attr}()'! "
                        "Repositories must never commit or rollback independently."
                    )


def test_append_only_repositories_lack_update_or_delete_apis() -> None:
    """Verify append-only repositories expose no generic update or delete methods."""
    from app.persistence.repositories.claim import ClaimRepository
    from app.persistence.repositories.source import SourceRepository

    # Forbidden method prefixes on append-only repositories
    forbidden_prefixes = ("update_", "delete_", "modify_", "replace_")

    for cls in (ClaimRepository, SourceRepository):
        methods = [
            name
            for name, member in inspect.getmembers(cls, predicate=inspect.isfunction)
            if not name.startswith("_")
        ]
        for m in methods:
            for prefix in forbidden_prefixes:
                assert not m.startswith(prefix), (
                    f"Append-only repository {cls.__name__} exposes prohibited mutation method '{m}'"
                )


def test_domain_layer_strict_independence() -> None:
    """Verify backend/app/domain/ contains ZERO references to SQLAlchemy or persistence modules."""
    domain_pkg = import_module("app.domain")
    assert domain_pkg.__file__ is not None
    domain_dir = os.path.dirname(domain_pkg.__file__)

    for filename in os.listdir(domain_dir):
        if filename.endswith(".py"):
            filepath = os.path.join(domain_dir, filename)
            with open(filepath) as f:
                content = f.read().lower()
                assert "sqlalchemy" not in content, (
                    f"Domain file {filename} violates boundary: imports/references SQLAlchemy"
                )
                assert "persistence" not in content, (
                    f"Domain file {filename} violates boundary: imports/references persistence layer"
                )
                assert "asyncsession" not in content, (
                    f"Domain file {filename} violates boundary: references AsyncSession"
                )


def test_outbox_event_create_defaults() -> None:
    """Verify OutboxEventCreate sets sensible default status PENDING and attempt_count 0."""
    ev = OutboxEventCreate(
        aggregate_type="dataset_version",
        aggregate_id=uuid.uuid4(),
        event_type="DATASET_VERSION_FINALIZED",
        payload={"version": 1},
    )
    assert ev.status == "PENDING"
    assert ev.attempt_count == 0
    assert ev.available_at is not None
    assert ev.project_id is None


def test_outbox_repository_scope_and_forbidden_worker_semantics() -> None:
    """Verify OutboxRepository contains ONLY persistence primitives and zero worker semantics."""
    from app.persistence.repositories.outbox import OutboxRepository

    public_methods = {
        name
        for name, member in inspect.getmembers(OutboxRepository, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    # Exact required primitives + bounded read-only query
    assert public_methods == {"enqueue", "get_by_id", "list_by_status"}

    # Prohibited queue consumption / worker semantic prefixes or methods
    prohibited_names = {
        "poll_pending",
        "claim_pending",
        "next_pending_batch",
        "claim_batch",
        "mark_processing",
        "lease",
        "heartbeat",
        "retry",
        "publish",
        "deliver",
    }
    assert public_methods.isdisjoint(prohibited_names)

    # Inspect AST of OutboxRepository to ensure no SQL locking or lease calls exist
    tree = ast.parse(inspect.getsource(OutboxRepository))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("with_for_update", "skip_locked", "claim", "lease")

    # Inspect source code of outbox.py for locking keywords
    outbox_file = inspect.getfile(OutboxRepository)
    with open(outbox_file) as f:
        src = f.read().lower()

    assert "for update" not in src
    assert "skip locked" not in src
