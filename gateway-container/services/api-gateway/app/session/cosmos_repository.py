"""[운영 세션 저장소] 대화 기록을 Azure Cosmos DB 에 영구 저장한다.

컨테이너 구조: 문서 id = session_id, 파티션 키 = /session_id.
컨테이너는 인프라(포털/IaC)에서 미리 만든다 — 코드가 임의로 DB 를 만들지 않아야
잘못된 계정에 쓰는 실수를 일찍 발견할 수 있다.

기술 배경 두 가지:
- Cosmos SDK 는 동기(응답을 기다리는 동안 서버가 멈춤)라서, 모든 public 메서드는
  asyncio.to_thread 로 별도 스레드에서 실행한다 → 스트리밍 중에도 서버가 안 멈춘다.
- 턴 추가는 "읽기 → 목록에 추가 → 다시 쓰기" 3단계다. 같은 세션에 요청 두 개가
  겹치면 나중 쓰기가 먼저 쓴 턴을 덮어쓸 수 있어서, etag(문서 버전표)로
  "내가 읽은 뒤 아무도 안 고쳤을 때만 쓰기"를 걸고, 충돌하면 다시 읽어 재시도한다.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from .. import settings
from .repository import iso, new_session_id, now_ts, turns_to_llm_messages, valid_session_id


class CosmosSessionRepository:
    def __init__(self) -> None:
        from azure.core import MatchConditions
        from azure.cosmos import CosmosClient
        from azure.cosmos import exceptions as cx

        # 예외 클래스들을 멤버로 보관 (아래 메서드들이 except 절에서 사용)
        self._not_found = cx.CosmosResourceNotFoundError          # 문서 없음
        self._conflict = cx.CosmosResourceExistsError             # 생성 시 이미 존재
        self._precondition = cx.CosmosAccessConditionFailedError  # etag 불일치(누가 먼저 씀)
        self._if_not_modified = MatchConditions.IfNotModified

        # 접속 정보: 연결 문자열 하나 또는 endpoint+key 조합
        conn = os.getenv("COSMOS_CONNECTION_STRING", "")
        if conn:
            client = CosmosClient.from_connection_string(conn)
        else:
            endpoint, key = os.getenv("COSMOS_ENDPOINT", ""), os.getenv("COSMOS_KEY", "")
            if not endpoint or not key:
                raise ValueError("cosmos requires COSMOS_ENDPOINT + COSMOS_KEY (or COSMOS_CONNECTION_STRING)")
            client = CosmosClient(endpoint, credential=key)

        database, container = os.getenv("COSMOS_DATABASE", ""), os.getenv("COSMOS_CONTAINER", "")
        if not database or not container:
            raise ValueError("cosmos requires COSMOS_DATABASE + COSMOS_CONTAINER")
        self._container = client.get_database_client(database).get_container_client(container)

    # --- 내부 동기 구현 (반드시 to_thread 를 통해서만 호출) ---

    def _read(self, sid: str) -> dict[str, Any] | None:
        """문서 하나 읽기. 없으면 None (예외를 밖으로 던지지 않는다)."""
        try:
            return self._container.read_item(item=sid, partition_key=sid)
        except self._not_found:
            return None

    @staticmethod
    def _to_snapshot(item: dict[str, Any]) -> dict[str, Any]:
        """DB 문서 → API 가 돌려주는 형태(snapshot)로 변환."""
        turns = list(item.get("turns") or [])
        return {"session_id": item["session_id"], "created_at": item["created_at"],
                "updated_at": item["updated_at"], "turn_count": len(turns), "turns": turns}

    def _new_item(self, sid: str) -> dict[str, Any]:
        now = now_ts()
        item = {"id": sid, "session_id": sid, "updated_ts": now,
                "created_at": iso(now), "updated_at": iso(now), "turns": []}
        if settings.SESSION_TTL_SECONDS > 0:
            item["ttl"] = settings.SESSION_TTL_SECONDS  # Cosmos 가 TTL 후 자동 삭제
        return item

    def _touch(self, item: dict[str, Any]) -> None:
        """갱신 시각과 TTL 을 새로 찍는다 (문서를 쓰기 직전에 호출)."""
        item["updated_ts"] = now_ts()
        item["updated_at"] = iso(item["updated_ts"])
        if settings.SESSION_TTL_SECONDS > 0:
            item["ttl"] = settings.SESSION_TTL_SECONDS

    def _create_sync(self, session_id: str | None) -> dict[str, Any]:
        item = self._new_item(valid_session_id(session_id) or new_session_id())
        self._container.upsert_item(body=item)  # upsert = 있으면 덮어쓰고 없으면 생성
        return self._to_snapshot(item)

    def _ensure_sync(self, session_id: str | None) -> dict[str, Any]:
        sid = valid_session_id(session_id)
        if not sid:
            return self._create_sync(None)
        item = self._read(sid)
        if item is None:
            return self._create_sync(sid)
        self._touch(item)
        try:
            # etag 조건부 쓰기: 내가 읽은 버전 그대로일 때만 교체
            self._container.replace_item(item=sid, body=item, etag=item.get("_etag"),
                                         match_condition=self._if_not_modified)
        except self._precondition:
            item = self._read(sid) or item  # 다른 요청이 먼저 갱신함 — 최신본을 반환만 한다
        return self._to_snapshot(item)

    def _append_turn_sync(self, session_id: str, turn: dict[str, Any]) -> dict[str, Any]:
        sid = valid_session_id(session_id) or new_session_id()
        clean = dict(turn)
        clean.setdefault("ts", iso())
        # 최대 4회 재시도: 동시 요청과 충돌하면 최신 문서를 다시 읽어 다시 쓴다 → 턴 유실 방지
        for _ in range(4):
            item = self._read(sid)
            if item is None:
                # 문서가 아직 없음 → 새로 생성. 동시에 다른 요청이 먼저 만들었으면(409) 재시도
                item = self._new_item(sid)
                item["turns"] = [clean]
                try:
                    self._container.create_item(body=item)
                    return self._to_snapshot(item)
                except self._conflict:
                    continue
            # 기존 문서에 턴 추가 (최대 개수 초과분은 앞에서부터 버림)
            item["turns"] = (list(item.get("turns") or []) + [clean])[-settings.SESSION_MAX_TURNS:]
            self._touch(item)
            try:
                self._container.replace_item(item=sid, body=item, etag=item.get("_etag"),
                                             match_condition=self._if_not_modified)
                return self._to_snapshot(item)
            except self._precondition:
                continue  # 다른 요청이 먼저 씀(412) → 최신본 기준으로 재시도
        raise RuntimeError(f"cosmos session write contention: {sid}")

    def _snapshot_sync(self, session_id: str) -> dict[str, Any] | None:
        sid = valid_session_id(session_id)
        if not sid:
            return None
        item = self._read(sid)
        return self._to_snapshot(item) if item else None

    # --- SessionRepository 규격 (async) — 동기 구현을 스레드로 감싼 것 ---

    async def create(self, session_id: str | None = None) -> dict[str, Any]:
        return await asyncio.to_thread(self._create_sync, session_id)

    async def ensure(self, session_id: str | None = None) -> dict[str, Any]:
        return await asyncio.to_thread(self._ensure_sync, session_id)

    async def append_turn(self, session_id: str, turn: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._append_turn_sync, session_id, turn)

    async def snapshot(self, session_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._snapshot_sync, session_id)

    async def recent_llm_messages(self, session_id: str, max_turns: int | None = None) -> list[dict[str, str]]:
        snap = await self.snapshot(session_id)
        if not snap:
            return []
        limit = max_turns if max_turns is not None else settings.SESSION_CONTEXT_TURNS
        return turns_to_llm_messages(snap.get("turns", [])[-limit:])
