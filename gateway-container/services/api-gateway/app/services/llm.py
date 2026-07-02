"""[LLM 창구] 답변 생성 AI(Azure OpenAI) 호출. 실제 통신은 common/llm_client.py.

클라이언트는 서버 시작 시가 아니라 "첫 호출 때" 만든다 — Azure 키가 없는
로컬 테스트 환경에서도 서버가 뜰 수 있게 하기 위해서다(테스트는 이 어댑터를
가짜로 교체하므로 실제 클라이언트가 만들어지지 않는다).
"""
from typing import AsyncIterator

from common.llm_client import LLMClient


class LlmAdapter:
    def __init__(self):
        self._client: LLMClient | None = None

    async def chat_stream_async(self, messages: list[dict], options: dict | None = None) -> AsyncIterator[str]:
        """LLM 답변을 글자 조각 단위로 흘려보낸다 (async generator)."""
        if self._client is None:
            self._client = LLMClient()  # 첫 호출 때 생성 — env 검증도 이때 일어난다
        async for token in self._client.chat_stream_async(messages, **llm_options(options)):
            yield token


def llm_options(options: dict | None) -> dict:
    """요청의 llm 옵션(max_completion_tokens/temperature)을 LLMClient 인자로 변환.

    숫자가 아닌 값이 오면 조용히 무시하고 서버 기본값을 쓴다 (요청 하나 때문에
    전체 응답이 실패하지 않도록).
    """
    kwargs: dict = {}
    if not options:
        return kwargs
    max_tokens = options.get("max_completion_tokens") or options.get("max_tokens")
    if max_tokens is not None:
        try:
            kwargs["max_tokens"] = int(max_tokens)
        except (TypeError, ValueError):
            pass
    temperature = options.get("temperature")
    if temperature is not None:
        try:
            kwargs["temperature"] = float(temperature)
        except (TypeError, ValueError):
            pass
    return kwargs
