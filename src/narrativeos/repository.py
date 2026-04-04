from __future__ import annotations

from .persistence.repositories import DEFAULT_DATABASE_URL, SQLAlchemyPlatformRepository


SQLAlchemyRepository = SQLAlchemyPlatformRepository

__all__ = ["DEFAULT_DATABASE_URL", "SQLAlchemyRepository", "SQLAlchemyPlatformRepository"]
