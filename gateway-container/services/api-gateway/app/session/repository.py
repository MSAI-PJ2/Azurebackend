"""세션 저장소 계약(Protocol) + 인메모리 구현(개발/테스트용). 운영은 cosmos_repository.

모든 메서드는 async — 네트워크 백엔드(Cosmos)가 이벤트루프를 막지 않게 하기 위한 계약.
Entra 도입 시 세션 문서에 user_id 를 넣어 "내 세션만 접근"을 이 계층에서 보장한다.
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from .. import settings

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class SessionRepository(Protocol):
    async def create(self, session_id: str | None = None) -> dict[str, Any]: ...
    async def ensure(self, session_id: str | None = None) -> dict[str, Any]: ...
    async def append_turn(self, session_id: str, turn: dict[str, Any]) -> dict[str, Any]: ...
    async def snapshot(self, session_id: str) -> dict[str, Any] | None: ...
    async def recent_llm_messages(self, session_id: str, max_turns: int | None = None) -> list[dict[str, str]]: ...


def now_ts() -> float:
    return time.time()


def iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or now_ts(), timezone.utc).isoformat()


def valid_session_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return value if _SESSION_ID_RE.match(value) else None


def new_session_id() -> str:
    return str(uuid.uuid4())


def turns_to_llm_messages(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    """저장된 턴 → LLM 대화 히스토리(role/content)."""
    return [{"role": t["role"], "content": (t.get("text") or "").strip()}
            for t in turns
            if t.get("role") in ("user", "assistant") and (t.get("text") or "").strip()]


# ---------------------------------------------------------------------------
# 인메모리 구현 — 레플리카 간 공유 안 됨, 재시작 시 소멸. 개발/테스트 전용.
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}


def _new_item(sid: str) -> dict[str, Any]:
    now = now_ts()
    return {"session_id": sid, "updated_ts": now,
            "created_at": iso(now), "updated_at": iso(now), "turns": []}


def _prune_locked() -> None:
    now = now_ts()
    for sid in [s for s, it in _sessions.items()
                if now - float(it.get("updated_ts", 0)) > settings.SESSION_TTL_SECONDS]:
        _sessions.pop(sid, None)


def _snapshot_locked(sid: str) -> dict[str, Any]:
    item = _sessions[sid]
    return {"session_id": sid, "created_at": item["created_at"], "updated_at": item["updated_at"],
            "turn_count": len(item["turns"]), "turns": list(item["turns"])}


class InMemorySessionRepository:
    async def create(self, session_id: str | None = None) -> dict[str, Any]:
        sid = valid_session_id(session_id) or new_session_id()
        with _lock:
            _prune_locked()
            _sessions[sid] = _new_item(sid)
            return _snapshot_locked(sid)

    async def ensure(self, session_id: str | None = None) -> dict[str, Any]:
        sid = valid_session_id(session_id)
        with _lock:
            _prune_locked()
            if sid and sid in _sessions:
                item = _sessions[sid]
                item["updated_ts"] = now_ts()
                item["updated_at"] = iso(item["updated_ts"])
                return _snapshot_locked(sid)
        return await self.create(sid)

    async def append_turn(self, session_id: str, turn: dict[str, Any]) -> dict[str, Any]:
        sid = valid_session_id(session_id) or new_session_id()
        with _lock:
            _prune_locked()
            item = _sessions.setdefault(sid, _new_item(sid))
            clean = dict(turn)
            clean.setdefault("ts", iso())
            item["turns"] = (item["turns"] + [clean])[-settings.SESSION_MAX_TURNS:]
            item["updated_ts"] = now_ts()
            item["updated_at"] = iso(item["updated_ts"])
            return _snapshot_locked(sid)

    async def snapshot(self, session_id: str) -> dict[str, Any] | None:
        sid = valid_session_id(session_id)
        with _lock:
            _prune_locked()
            return _snapshot_locked(sid) if sid and sid in _sessions else None

    async def recent_llm_messages(self, session_id: str, max_turns: int | None = None) -> list[dict[str, str]]:
        sid = valid_session_id(session_id)
        limit = max_turns if max_turns is not None else settings.SESSION_CONTEXT_TURNS
        with _lock:
            item = _sessions.get(sid) if sid else None
            turns = list(item["turns"][-limit:]) if item else []
        return turns_to_llm_messages(turns)
