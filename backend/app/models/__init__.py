"""SQLAlchemy ORM models for Film Kit Studio backend.

This package contains the ORM models that map to the PostgreSQL schema
described in ARCHITECTURE.md. Each model corresponds to a domain entity
in the OiiOii.ai clone (Users, Projects, Assets, Styles, Models,
Agent Executions).

Models are intentionally thin data containers; business logic lives in
the service layer (app/services). Importing this package registers all
models with SQLAlchemy's declarative Base so Alembic can detect them.
"""

from app.models.user import User
from app.models.project import Project
from app.models.asset import Asset
from app.models.style import Style
from app.models.model import Model
from app.models.agent_execution import AgentExecution

__all__ = [
    "User",
    "Project",
    "Asset",
    "Style",
    "Model",
    "AgentExecution",
]
