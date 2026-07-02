"""Azure Cosmos DB 세션 저장소 (운영). 컨테이너: item id = session_id, PK = /session_id.

SDK 는 블로킹이라 public 메서드는 to_thread 로 오프로딩. 턴 추가는 etag 조건부
replace + 재시도 — 같은 세션에 동시 요청이 겹쳐도 턴이 유실되지 않는다.
컨테이너는 인프라에서 미리 생성한다(런타임 생성 금지 — 계정 실수 조기 발견).
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

        self._not_found = cx.CosmosResourceNotFoundError
        self._conflict = cx.CosmosResourceExistsError
        self._precondition = cx.CosmosAccessConditionFailedError
        self._if_not_modified = MatchConditions.IfNotModified

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

    # --- 내부 동기 구현 (to_thread 로만 호출) ---

    def _read(self, sid: str) -> dict[str, Any] | None:
        try:
            return self._container.read_item(item=sid, partition_key=sid)
        except self._not_found:
            return None

    @staticmethod
    def _to_snapshot(item: dict[str, Any]) -> dict[str, Any]:
        turns = list(item.get("turns") or [])
        return {"session_id": item["session_id"], "created_at": item["created_at"],
                "updated_at": item["updated_at"], "turn_count": len(turns), "turns": turns}

    def _new_item(self, sid: str) -> dict[str, Any]:
        now = now_ts()
        item = {"id": sid, "session_id": sid, "updated_ts": now,
                "created_at": iso(now), "updated_at": iso(now), "turns": []}
        if settings.SESSION_TTL_SECONDS > 0:
            item["ttl"] = settings.SESSION_TTL_SECONDS
        return item

    def _touch(self, item: dict[str, Any]) -> None:
        item["updated_ts"] = now_ts()
        item["updated_at"] = iso(item["updated_ts"])
        if settings.SESSION_TTL_SECONDS > 0:
            item["ttl"] = settings.SESSION_TTL_SECONDS

    def _create_sync(self, session_id: str | None) -> dict[str, Any]:
        item = self._new_item(valid_session_id(session_id) or new_session_id())
        self._container.upsert_item(body=item)
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
            self._container.replace_item(item=sid, body=item, etag=item.get("_etag"),
                                         match_condition=self._if_not_modified)
        except self._precondition:
            item = self._read(sid) or item  # 동시 쓰기가 이미 갱신 — 최신본 반환
        return self._to_snapshot(item)

    def _append_turn_sync(self, session_id: str, turn: dict[str, Any]) -> dict[str, Any]:
        sid = valid_session_id(session_id) or new_session_id()
        clean = dict(turn)
        clean.setdefault("ts", iso())
        for _ in range(4):  # etag 충돌 시 최신본 기준 재시도 → 턴 유실 방지
            item = self._read(sid)
            if item is None:
                item = self._new_item(sid)
                item["turns"] = [clean]
                try:
                    self._container.create_item(body=item)
                    return self._to_snapshot(item)
                except self._conflict:
                    continue
            item["turns"] = (list(item.get("turns") or []) + [clean])[-settings.SESSION_MAX_TURNS:]
            self._touch(item)
            try:
                self._container.replace_item(item=sid, body=item, etag=item.get("_etag"),
                                             match_condition=self._if_not_modified)
                return self._to_snapshot(item)
            except self._precondition:
                continue
        raise RuntimeError(f"cosmos session write contention: {sid}")

    def _snapshot_sync(self, session_id: str) -> dict[str, Any] | None:
        sid = valid_session_id(session_id)
        if not sid:
            return None
        item = self._read(sid)
        return self._to_snapshot(item) if item else None

    # --- SessionRepository 계약 (async) ---

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
