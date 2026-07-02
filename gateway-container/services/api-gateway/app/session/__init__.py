"""[세션 선택] 환경변수 SESSION_REPOSITORY 에 따라 대화 기록 저장소를 고른다.

    memory  서버 메모리에 저장 — 개발/테스트용 (재시작하면 사라짐, 기본값)
    cosmos  Azure Cosmos DB 에 저장 — 운영용 (영구 보존, 서버 여러 대에서 공유)

서버 시작 시 한 번 선택되고, 이후 코드는 session_repository 만 쓰면 된다.
"""
from .. import settings
from .repository import InMemorySessionRepository, SessionRepository


def _build() -> SessionRepository:
    backend = settings.SESSION_REPOSITORY.strip().lower()
    if backend in ("", "memory"):
        return InMemorySessionRepository()
    if backend == "cosmos":
        # cosmos 선택 시에만 import — memory 로 쓸 때는 azure-cosmos 패키지가 없어도 된다
        from .cosmos_repository import CosmosSessionRepository
        return CosmosSessionRepository()
    raise ValueError("Unsupported SESSION_REPOSITORY: " + settings.SESSION_REPOSITORY)


session_repository: SessionRepository = _build()
