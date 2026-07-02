"""Azure Cosmos DB NoSQL 세션 저장소 (운영).

컨테이너 형태:
    item id = session_id, partition key = /session_id

컨테이너는 인프라(포털/IaC)에서 미리 만든다 — 런타임에 DB/컨테이너를 생성하지
않아서 잘못된 계정에 쓰는 실수를 조기에 드러낸다.

Cosmos Python SDK 는 동기(블로킹)라서, 모든 public 메서드는 asyncio.to_thread 로
오프로딩한다. SSE 스트리밍 중 세션 쓰기가 이벤트루프를 막지 않게 하기 위함이다.

동시성: 턴 추가는 read → append → replace 인데, 같은 session_id 로 요청이 겹치면
마지막 쓰기가 앞의 턴을 덮어쓸 수 있다. 그래서 replace 는 etag 조건부
(IfNotModified)로 수행하고, 충돌(412) 시 다시 읽어 재시도한다 — 턴 유실 방지.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from ..core import settings
from .repository import iso, new_session_id, now_ts, turns_to_llm_messages, valid_session_id


def _env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


class CosmosSessionRepository:
    def __init__(self) -> None:
        try:
            from azure.core import MatchConditions
            from azure.cosmos import CosmosClient
            from azure.cosmos.exceptions import (
                CosmosAccessConditionFailedError,
                CosmosResourceExistsError,
                CosmosResourceNotFoundError,
            )
        except ImportError as exc:  # pragma: no cover - 의존성 누락 시에만
            raise RuntimeError("SESSION_REPOSITORY=cosmos requires azure-cosmos package") from exc

        self._not_found_error = CosmosResourceNotFoundError
        self._conflict_error = CosmosResourceExistsError
        self._precondition_error = CosmosAccessConditionFailedError
        self._if_not_modified = MatchConditions.IfNotModified
        connection_string = _env_first("COSMOS_CONNECTION_STRING", "AZURE_COSMOS_CONNECTION_STRING")
        endpoint = _env_first("COSMOS_ENDPOINT", "COSMOS_SESSION_ENDPOINT", "AZURE_COSMOS_ENDPOINT")
        key = _env_first("COSMOS_KEY", "COSMOS_SESSION_KEY", "AZURE_COSMOS_KEY")
        database_name = _env_first("COSMOS_DATABASE", "COSMOS_SESSION_DATABASE", "AZURE_COSMOS_DATABASE")
        container_name = _env_first("COSMOS_CONTAINER", "COSMOS_SESSION_CONTAINER", "AZURE_COSMOS_CONTAINER")

        if connection_string:
            client = CosmosClient.from_connection_string(connection_string)
        else:
            missing = [
                name
                for name, value in {
                    "COSMOS_ENDPOINT(or COSMOS_SESSION_ENDPOINT)": endpoint,
                    "COSMOS_KEY(or COSMOS_SESSION_KEY)": key,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError("Cosmos session repository missing env vars: " + ", ".join(missing))
            client = CosmosClient(endpoint, credential=key)

        missing_store = [
            name
            for name, value in {
                "COSMOS_DATABASE(or COSMOS_SESSION_DATABASE)": database_name,
                "COSMOS_CONTAINER(or COSMOS_SESSION_CONTAINER)": container_name,
            }.items()
            if not value
        ]
        if missing_store:
            raise ValueError("Cosmos session repository missing env vars: " + ", ".join(missing_store))

        self._container = client.get_database_client(database_name).get_container_client(container_name)

    # ------------------------------------------------------------------
    # 내부 동기 구현 (Cosmos SDK 호출 — 반드시 to_thread 로 감싸서 사용)
    # ------------------------------------------------------------------

    def _read(self, session_id: str) -> dict[str, Any] | None:
        try:
            return self._container.read_item(item=session_id, partition_key=session_id)
        except self._not_found_error:
            return None

    @staticmethod
    def _to_snapshot(item: dict[str, Any]) -> dict[str, Any]:
        turns = list(item.get("turns") or [])
        return {
            "session_id": item["session_id"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
            "turn_count": len(turns),
            "turns": turns,
        }

    @staticmethod
    def _new_item(session_id: str) -> dict[str, Any]:
        now = now_ts()
        item: dict[str, Any] = {
            "id": session_id,
            "session_id": session_id,
            "created_ts": now,
            "updated_ts": now,
            "created_at": iso(now),
            "updated_at": iso(now),
            "turns": [],
        }
        if settings.SESSION_TTL_SECONDS > 0:
            item["ttl"] = settings.SESSION_TTL_SECONDS
        return item

    def _touch(self, item: dict[str, Any]) -> None:
        now = now_ts()
        item["updated_ts"] = now
        item["updated_at"] = iso(now)
        if settings.SESSION_TTL_SECONDS > 0:
            item["ttl"] = settings.SESSION_TTL_SECONDS

    def _create_sync(self, session_id: str | None) -> dict[str, Any]:
        sid = valid_session_id(session_id) or new_session_id()
        item = self._new_item(sid)
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
            self._container.replace_item(
                item=sid, body=item,
                etag=item.get("_etag"), match_condition=self._if_not_modified,
            )
        except self._precondition_error:
            # 동시 쓰기가 이미 문서를 갱신함(touch 목적 달성) — 최신본을 반환만 한다
            item = self._read(sid) or item
        return self._to_snapshot(item)

    def _append_turn_sync(self, session_id: str, turn: dict[str, Any]) -> dict[str, Any]:
        sid = valid_session_id(session_id) or new_session_id()
        clean_turn = dict(turn)
        clean_turn.setdefault("ts", iso())

        # etag 조건부 쓰기 + 재시도: 같은 세션에 동시 요청이 겹쳐도 턴이 유실되지 않는다
        for _ in range(4):
            item = self._read(sid)

            if item is None:
                item = self._new_item(sid)
                item["turns"] = [clean_turn]
                self._touch(item)
                try:
                    self._container.create_item(body=item)
                    return self._to_snapshot(item)
                except self._conflict_error:
                    continue  # 다른 요청이 먼저 생성함 — 다시 읽어 append 경로로

            turns = list(item.get("turns") or [])
            turns.append(clean_turn)
            if len(turns) > settings.SESSION_MAX_TURNS:
                turns = turns[-settings.SESSION_MAX_TURNS:]
            item["turns"] = turns
            self._touch(item)
            try:
                self._container.replace_item(
                    item=sid, body=item,
                    etag=item.get("_etag"), match_condition=self._if_not_modified,
                )
                return self._to_snapshot(item)
            except self._precondition_error:
                continue  # 다른 요청이 먼저 썼음 — 최신본 기준으로 재시도

        raise RuntimeError(f"cosmos session write contention: {sid}")

    def _snapshot_sync(self, session_id: str) -> dict[str, Any] | None:
        sid = valid_session_id(session_id)
        if not sid:
            return None
        item = self._read(sid)
        return self._to_snapshot(item) if item else None

    # ------------------------------------------------------------------
    # SessionRepository 계약 (async)
    # ------------------------------------------------------------------

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
