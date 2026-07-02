"""[검색 창구] 상담 기법 참고자료 검색(RAG). 실제 검색은 retrieve/client.py 의 Azure AI Search.

검색 SDK 는 동기(결과가 올 때까지 서버를 세워 둠)라서 asyncio.to_thread 로
별도 스레드에 맡긴다 — 그래야 respond_flow 의 gather 에서 안전검사·분류와
"동시에" 실행될 수 있다. 클라이언트는 첫 호출 때 생성(env 지연 검증).
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
