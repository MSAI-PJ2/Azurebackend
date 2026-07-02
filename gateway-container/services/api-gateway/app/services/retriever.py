"""RAG 검색 어댑터 (Azure AI Search, retrieve/client.py).

검색 API 는 동기라서 스레드로 오프로딩 — safety/classify 와의 gather 병렬성 유지.
클라이언트는 첫 호출 시 생성(env 지연 검증).
"""
import asyncio

from retrieve.client import AzureAiSearchRetriever


class RetrieverAdapter:
    def __init__(self):
        self._retriever: AzureAiSearchRetriever | None = None

    async def retrieve(self, text: str) -> list[dict]:
        if self._retriever is None:
            self._retriever = AzureAiSearchRetriever()
        return await asyncio.to_thread(self._retriever.retrieve, text)
