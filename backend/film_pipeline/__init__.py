"""Durable, credit-safe consumption layer for long-form film generation.

This package intentionally talks to the supply layer only through the frozen HTTP
contracts.  It does not import or inspect the provider/router implementation.
"""

from .clients import ChatPoolClient, VideoRouterClient
from .crew import ApprovedCrewHandoff, CrewHandoffError, admit_approved_crew_film, build_approved_crew_handoff
from .orchestrator import FilmOrchestrator, FilmRequest
from .store import FilmJobStore

__all__ = [
    "ApprovedCrewHandoff", "ChatPoolClient", "CrewHandoffError", "FilmJobStore", "FilmOrchestrator", "FilmRequest",
    "VideoRouterClient", "admit_approved_crew_film", "build_approved_crew_handoff",
]
