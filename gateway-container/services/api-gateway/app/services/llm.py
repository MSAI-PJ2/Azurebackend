"""LLM 어댑터 (Azure OpenAI, common/llm_client.py). 클라이언트는 첫 호출 시 생성(env 지연 검증)."""
from typing import AsyncIterator

from common.llm_client import LLMClient


class LlmAdapter:
    def __init__(self):
        self._client: LLMClient | None = None

    async def chat_stream_async(self, messages: list[dict], options: dict | None = None) -> AsyncIterator[str]:
        if self._client is None:
            self._client = LLMClient()
        async for token in self._client.chat_stream_async(messages, **llm_options(options)):
            yield token


def llm_options(options: dict | None) -> dict:
    """요청 레벨 옵션(max_completion_tokens/temperature) → LLMClient kwargs."""
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
