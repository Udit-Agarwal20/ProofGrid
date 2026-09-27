"""Entity and entity match persistence repository."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select

from app.db.models.entity import Entity, EntityMatch
from app.persistence.errors import PersistenceIntegrityError
from app.persistence.repositories.base import BaseRepository


class EntityRepository(BaseRepository):
    """Persistence operations for resolved entities and pairwise match decisions."""

    # -------------------------------------------------------------------------
    # Entities
    # -------------------------------------------------------------------------

    def add_entity(self, entity: Entity) -> Entity:
        """Stage an entity for insertion."""
        self._session.add(entity)
        return entity

    async def get_entity(self, entity_id: uuid.UUID) -> Entity | None:
        """Retrieve an entity by its ID."""
        return await self._session.get(Entity, entity_id)

    async def get_by_stable_key(
        self,
        project_id: uuid.UUID,
        stable_key: str,
    ) -> Entity | None:
        """Retrieve an entity by its tenant-scoped stable key."""
        stmt = select(Entity).where(
            Entity.project_id == project_id,
            Entity.stable_entity_key == stable_key,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_entities_for_project(
        self,
        project_id: uuid.UUID,
        entity_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Entity]:
        """List entities for a project optionally filtered by entity type."""
        stmt = select(Entity).where(Entity.project_id == project_id)
        if entity_type is not None:
            stmt = stmt.where(Entity.entity_type == entity_type)
        stmt = stmt.order_by(Entity.canonical_name.asc()).offset(offset).limit(limit)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Entity Matches (Canonical Pair Ordering)
    # -------------------------------------------------------------------------

    def add_entity_match(
        self,
        project_id: uuid.UUID,
        entity_a_id: uuid.UUID,
        entity_b_id: uuid.UUID,
        decision: str,
        signals: dict[str, Any] | None = None,
        score: Decimal | float | None = None,
        reason: dict[str, Any] | None = None,
    ) -> EntityMatch:
        """Stage an entity match decision with automatic canonical UUID ordering.

        Enforces source_entity_id < target_entity_id prior to insertion, adhering
        to the database check constraint and preventing reversed duplicate pairs.
        """
        if entity_a_id == entity_b_id:
            raise PersistenceIntegrityError(
                f"Cannot create an entity match between an entity and itself: {entity_a_id}",
                constraint_name="ck_entity_matches_canonical_pair_order",
            )

        source_id, target_id = (
            (entity_a_id, entity_b_id) if entity_a_id < entity_b_id else (entity_b_id, entity_a_id)
        )

        match = EntityMatch(
            project_id=project_id,
            source_entity_id=source_id,
            target_entity_id=target_id,
            decision=decision,
            signals=signals or {},
            score=Decimal(str(score)) if score is not None else None,
            reason=reason or {},
        )
        self._session.add(match)
        return match

    async def get_entity_match(
        self,
        project_id: uuid.UUID,
        entity_a_id: uuid.UUID,
        entity_b_id: uuid.UUID,
    ) -> EntityMatch | None:
        """Retrieve a pairwise entity match decision regardless of argument order."""
        if entity_a_id == entity_b_id:
            return None

        source_id, target_id = (
            (entity_a_id, entity_b_id) if entity_a_id < entity_b_id else (entity_b_id, entity_a_id)
        )

        stmt = select(EntityMatch).where(
            EntityMatch.project_id == project_id,
            EntityMatch.source_entity_id == source_id,
            EntityMatch.target_entity_id == target_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_entity_matches_for_entity(
        self,
        entity_id: uuid.UUID,
        limit: int = 50,
    ) -> list[EntityMatch]:
        """List all pairwise match decisions involving a given entity."""
        stmt = (
            select(EntityMatch)
            .where(
                or_(
                    EntityMatch.source_entity_id == entity_id,
                    EntityMatch.target_entity_id == entity_id,
                )
            )
            .order_by(EntityMatch.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
