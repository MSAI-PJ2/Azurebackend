"""세션 저장소 — SESSION_REPOSITORY: memory(개발/테스트, 기본) | cosmos(운영)."""
from .. import settings
from .repository import InMemorySessionRepository, SessionRepository


def _build() -> SessionRepository:
    backend = settings.SESSION_REPOSITORY.strip().lower()
    if backend in ("", "memory"):
        return InMemorySessionRepository()
    if backend == "cosmos":
        from .cosmos_repository import CosmosSessionRepository
        return CosmosSessionRepository()
    raise ValueError("Unsupported SESSION_REPOSITORY: " + settings.SESSION_REPOSITORY)


session_repository: SessionRepository = _build()
