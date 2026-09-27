"""Project repository for tenancy and workspace persistence."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models.project import Project
from app.persistence.repositories.base import BaseRepository


class ProjectRepository(BaseRepository):
    """Persistence operations for tenant workspace projects."""

    def add(self, project: Project) -> Project:
        """Stage a new project for insertion within the current Unit of Work."""
        self._session.add(project)
        return project

    async def get_by_id(self, project_id: uuid.UUID) -> Project | None:
        """Retrieve a project by its primary key ID."""
        return await self._session.get(Project, project_id)

    async def get_by_slug(self, slug: str) -> Project | None:
        """Retrieve a project by its unique workspace slug."""
        stmt = select(Project).where(Project.slug == slug)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_projects(self, limit: int = 50, offset: int = 0) -> list[Project]:
        """List projects with bounded pagination ordered by creation time."""
        stmt = select(Project).order_by(Project.created_at.desc()).offset(offset).limit(limit)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
