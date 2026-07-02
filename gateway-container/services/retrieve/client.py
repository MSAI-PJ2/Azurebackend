"""Azure AI Search retriever. 계약: retrieve(text, k) -> list[{id, content, score, metadata}].

필요 env: AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_API_KEY / AZURE_SEARCH_INDEX.
선택 env: AZURE_SEARCH_CONTENT_FIELD(기본 content), AZURE_SEARCH_ID_FIELD(기본 id),
AZURE_SEARCH_SEMANTIC_CONFIG(설정 시 시맨틱 랭킹), AZURE_SEARCH_SELECT_FIELDS(csv).
"""
from __future__ import annotations

import os
from typing import Any

from .types import RetrievedDoc


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
        value = (value or "").strip().rstrip("/")
        if not value or value.startswith("http"):
            return value
        return value if "://" in value else (
            "https://" + value if ".search.windows.net" in value
            else f"https://{value}.search.windows.net")

    def _search(self, text: str, k: int, *, semantic: bool):
        kwargs: dict[str, Any] = {"search_text": text, "top": k}
        if self.select_fields:
            kwargs["select"] = self.select_fields
        if semantic and self.semantic_config:
            kwargs["query_type"] = "semantic"
            kwargs["semantic_configuration_name"] = self.semantic_config
        return self.client.search(**kwargs)

    def retrieve(self, text: str, k: int = 8) -> list[RetrievedDoc]:
        query = (text or "").strip()
        if not query:
            return []
        try:
            results = self._search(query, k, semantic=bool(self.semantic_config))
        except Exception:
            # 시맨틱 설정 이름 오타 등으로 실패하면 keyword 검색으로 폴백 (응답 실패 방지)
            if not self.semantic_config:
                raise
            results = self._search(query, k, semantic=False)

        docs: list[RetrievedDoc] = []
        for idx, row in enumerate(results, start=1):
            doc = dict(row)
            content = str(doc.get(self.content_field) or "").strip()
            if not content:
                continue
            score = doc.get("@search.reranker_score") or doc.get("@search.score") or 0.0
            metadata = {k2: v for k2, v in doc.items()
                        if not k2.startswith("@search.") and k2 not in (self.content_field, self.id_field)}
            metadata["search_score"] = doc.get("@search.score")
            docs.append({"id": str(doc.get(self.id_field) or f"azure-search-{idx}"),
                         "content": content, "score": float(score), "metadata": metadata})
        return docs[:k]
