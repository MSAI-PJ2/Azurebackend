"""[세션 저장소] 대화 기록(턴)을 저장/조회하는 규격 + 인메모리 구현(개발용).

세션 = 대화방 하나. 턴 = 발화 하나(사용자 또는 AI). 세션 문서 형태:
    {session_id, created_at, updated_at, turns: [턴, 턴, ...]}

SessionRepository(Protocol) = "저장소라면 이 5개 메서드를 가져야 한다"는 규격 선언.
memory/cosmos 두 구현이 같은 규격을 따르므로 나머지 코드는 어느 쪽인지 몰라도 된다.
모든 메서드가 async 인 이유: Cosmos(네트워크 DB) 호출이 서버를 세워 두지 않게 하는
규격을 강제하기 위해서다. 운영 구현은 cosmos_repository.py.

Entra 로그인 도입 시(auth.py 가이드) 세션 문서에 user_id 를 넣어
"내 세션만 접근"을 이 계층에서 보장한다.
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from .. import settings

# 허용하는 session_id 형식: 영문/숫자/일부 기호, 최대 128자 (이상한 값 저장 방지)
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class SessionRepository(Protocol):
    async def create(self, session_id: str | None = None) -> dict[str, Any]: ...
    async def ensure(self, session_id: str | None = None) -> dict[str, Any]: ...          # 없으면 만들고, 있으면 갱신
    async def append_turn(self, session_id: str, turn: dict[str, Any]) -> dict[str, Any]: ...
    async def snapshot(self, session_id: str) -> dict[str, Any] | None: ...               # 현재 상태 조회
    async def recent_llm_messages(self, session_id: str, max_turns: int | None = None) -> list[dict[str, str]]: ...


# --- 공용 헬퍼 (memory/cosmos 양쪽에서 사용) ---

def now_ts() -> float:
    return time.time()


def iso(ts: float | None = None) -> str:
    """사람이 읽을 수 있는 시각 문자열 (UTC, 예: 2026-07-02T05:00:00+00:00)."""
    return datetime.fromtimestamp(ts or now_ts(), timezone.utc).isoformat()


def valid_session_id(value: str | None) -> str | None:
    """형식에 맞는 session_id 만 통과시킨다. 아니면 None."""
    if not value:
        return None
    value = value.strip()
    return value if _SESSION_ID_RE.match(value) else None


def new_session_id() -> str:
    return str(uuid.uuid4())  # 전 세계적으로 겹치지 않는 무작위 ID


def turns_to_llm_messages(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    """저장된 턴들 → LLM 이 이해하는 대화 형식([{role, content}, ...])으로 변환.

    텍스트가 없는 턴(STT 실패 기록 등)과 crisis 기록은 role/text 조건에서 걸러진다.
    """
    return [{"role": t["role"], "content": (t.get("text") or "").strip()}
            for t in turns
            if t.get("role") in ("user", "assistant") and (t.get("text") or "").strip()]


# ---------------------------------------------------------------------------
# 인메모리 구현 — 서버 메모리(dict)에 저장. 재시작하면 사라지고 서버 간 공유 안 됨.
# 개발/테스트 전용이며, 운영은 cosmos_repository.py 를 쓴다.
# ---------------------------------------------------------------------------

_lock = threading.Lock()   # 여러 요청이 동시에 dict 를 고칠 때 꼬이지 않게 하는 잠금
_sessions: dict[str, dict[str, Any]] = {}


def _new_item(sid: str) -> dict[str, Any]:
    now = now_ts()
    return {"session_id": sid, "updated_ts": now,
            "created_at": iso(now), "updated_at": iso(now), "turns": []}


def _prune_locked() -> None:
    """유효시간(TTL)이 지난 세션을 정리한다 (_lock 을 잡은 상태에서만 호출)."""
    now = now_ts()
    for sid in [s for s, it in _sessions.items()
                if now - float(it.get("updated_ts", 0)) > settings.SESSION_TTL_SECONDS]:
        _sessions.pop(sid, None)


def _snapshot_locked(sid: str) -> dict[str, Any]:
    """저장된 원본이 아니라 복사본을 돌려준다 (밖에서 고쳐도 원본이 안 바뀌게)."""
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
        """세션이 있으면 갱신시각만 업데이트, 없으면 새로 만든다."""
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
        """턴 하나를 뒤에 붙인다. 최대 개수(SESSION_MAX_TURNS)를 넘으면 앞에서부터 버린다."""
        sid = valid_session_id(session_id) or new_session_id()
        with _lock:
            _prune_locked()
            item = _sessions.setdefault(sid, _new_item(sid))
            clean = dict(turn)
            clean.setdefault("ts", iso())  # 저장 시각 기록
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
        """LLM 에 넘길 최근 대화 — 기본은 최근 SESSION_CONTEXT_TURNS(6)개 턴."""
        sid = valid_session_id(session_id)
        limit = max_turns if max_turns is not None else settings.SESSION_CONTEXT_TURNS
        with _lock:
            item = _sessions.get(sid) if sid else None
            turns = list(item["turns"][-limit:]) if item else []
        return turns_to_llm_messages(turns)
