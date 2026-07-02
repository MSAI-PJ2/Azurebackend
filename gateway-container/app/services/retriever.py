"""[검색 창구] 상담 기법 참고자료 검색(RAG) — Azure AI Search.

검색 계약: retrieve(text, k) -> [{id, content, score, metadata}, ...] (score 높을수록 관련 ↑)
필요 환경변수: AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_API_KEY / AZURE_SEARCH_INDEX.
선택 환경변수: AZURE_SEARCH_CONTENT_FIELD(기본 content), AZURE_SEARCH_ID_FIELD(기본 id),
AZURE_SEARCH_SEMANTIC_CONFIG(설정 시 시맨틱 랭킹), AZURE_SEARCH_SELECT_FIELDS(csv).

검색 SDK 는 동기(블로킹)라서 어댑터가 asyncio.to_thread 로 별도 스레드에 맡긴다 —
respond_flow 의 gather 에서 안전검사·분류와 "동시에" 실행되기 위함.
클라이언트는 첫 호출 때 생성 (키 없는 로컬 테스트에서도 서버가 뜨게).
"""
from __future__ import annotations

import asyncio
import os
from typing import Any


class AzureAiSearchRetriever:
    def __init__(self) -> None:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        self.endpoint = self._normalize_endpoint(os.getenv("AZURE_SEARCH_ENDPOINT", ""))
        self.api_key = os.getenv("AZURE_SEARCH_API_KEY", "")
        self.index = os.getenv("AZURE_SEARCH_INDEX", "")
        missing = [n for n, v in {"AZURE_SEARCH_ENDPOINT": self.endpoint,
                                  "AZURE_SEARCH_API_KEY": self.api_key,
                                  "AZURE_SEARCH_INDEX": self.index}.items() if not v]
        if missing:
            raise ValueError("Missing Azure AI Search env vars: " + ", ".join(missing))

        self.content_field = os.getenv("AZURE_SEARCH_CONTENT_FIELD", "content")
        self.id_field = os.getenv("AZURE_SEARCH_ID_FIELD", "id")
        self.semantic_config = os.getenv("AZURE_SEARCH_SEMANTIC_CONFIG", "")
        select = [f.strip() for f in os.getenv("AZURE_SEARCH_SELECT_FIELDS", "").split(",") if f.strip()]
        self.select_fields = select or None
        self.client = SearchClient(endpoint=self.endpoint, index_name=self.index,
                                   credential=AzureKeyCredential(self.api_key))

    @staticmethod
    def _normalize_endpoint(value: str) -> str:
        """서비스 이름만 적어도 완전한 주소(https://...search.windows.net)로 보정한다."""
        value = (value or "").strip().rstrip("/")
        if not value or value.startswith("http"):
            return value
        return value if "://" in value else (
            "https://" + value if ".search.windows.net" in value
            else f"https://{value}.search.windows.net")

    def _search(self, text: str, k: int, *, semantic: bool):
        """검색 실행. semantic=True 면 Azure 의 의미 기반 재랭킹을 추가로 쓴다."""
        kwargs: dict[str, Any] = {"search_text": text, "top": k}
        if self.select_fields:
            kwargs["select"] = self.select_fields
        if semantic and self.semantic_config:
            kwargs["query_type"] = "semantic"
            kwargs["semantic_configuration_name"] = self.semantic_config
        return self.client.search(**kwargs)

    def retrieve(self, text: str, k: int = 8) -> list[dict]:
        query = (text or "").strip()
        if not query:
            return []
        try:
            results = self._search(query, k, semantic=bool(self.semantic_config))
        except Exception:
            # 시맨틱 설정 이름 오타 등으로 실패하면 일반 키워드 검색으로 한 번 더 시도
            # (검색 실패로 상담 응답 전체가 죽는 것을 막는다)
            if not self.semantic_config:
                raise
            results = self._search(query, k, semantic=False)

        docs: list[dict] = []
        for idx, row in enumerate(results, start=1):
            doc = dict(row)
            content = str(doc.get(self.content_field) or "").strip()
            if not content:
                continue  # 본문이 없는 문서는 프롬프트에 넣어도 의미가 없어 건너뛴다
            # 점수: 시맨틱 재랭킹 점수가 있으면 그것을, 없으면 기본 검색 점수를 쓴다
            score = doc.get("@search.reranker_score") or doc.get("@search.score") or 0.0
            # 본문/ID/검색 내부 필드를 뺀 나머지를 metadata 로 보존 (예: distortions 라벨)
            metadata = {k2: v for k2, v in doc.items()
                        if not k2.startswith("@search.") and k2 not in (self.content_field, self.id_field)}
            metadata["search_score"] = doc.get("@search.score")
            docs.append({"id": str(doc.get(self.id_field) or f"azure-search-{idx}"),
                         "content": content, "score": float(score), "metadata": metadata})
        return docs[:k]


class RetrieverAdapter:
    def __init__(self):
        self._retriever: AzureAiSearchRetriever | None = None

    async def retrieve(self, text: str) -> list[dict]:
        if self._retriever is None:
            self._retriever = AzureAiSearchRetriever()
        return await asyncio.to_thread(self._retriever.retrieve, text)
