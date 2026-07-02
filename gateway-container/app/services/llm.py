"""[LLM 창구] 답변 생성 — Azure OpenAI Chat Completions (async 스트리밍 전용).

필요 환경변수: AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / AZURE_OPENAI_DEPLOYMENT.
토큰(답변 길이) 상한: AZURE_OPENAI_MAX_COMPLETION_TOKENS 가 기본값이자 상한이고,
더 높은 상한이 필요하면 *_LIMIT 로 분리해 지정한다.
클라이언트는 첫 호출 때 생성한다 — 키 없는 로컬 테스트에서도 서버가 뜨게
(테스트는 이 어댑터를 가짜로 교체하므로 실제 클라이언트가 만들어지지 않는다).
"""
from __future__ import annotations

import os
from typing import AsyncIterator

from openai import AsyncAzureOpenAI


def _int_env(name: str) -> int | None:
    """환경변수를 정수로 읽는다. 없거나 숫자가 아니면 None."""
    raw = os.getenv(name)
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


class LLMClient:
    """Azure OpenAI 에 실제로 접속해 답변을 스트리밍으로 받아오는 클라이언트."""

    def __init__(self):
        # 필수 환경변수 3개 확인 — 빠진 게 있으면 이름을 알려주며 즉시 실패
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")  # 배포한 모델 이름 (예: gpt-4.1-mini)
        missing = [n for n, v in {"AZURE_OPENAI_ENDPOINT": endpoint,
                                  "AZURE_OPENAI_API_KEY": api_key,
                                  "AZURE_OPENAI_DEPLOYMENT": deployment}.items() if not v]
        if missing:
            raise ValueError("Azure OpenAI missing env vars: " + ", ".join(missing))
        self.model = deployment
        # Async 클라이언트: 응답을 기다리는 동안 서버가 다른 요청을 처리할 수 있다
        self.client = AsyncAzureOpenAI(
            azure_endpoint=endpoint, api_key=api_key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"))

    @staticmethod
    def _token_limit(requested: int | None, fallback: int = 900) -> int:
        """요청 토큰 상한을 서버측 한도 안에서 결정 — 비용/지연 폭주 방지."""
        default = _int_env("AZURE_OPENAI_MAX_COMPLETION_TOKENS") or fallback
        desired = max(1, requested) if requested else default
        upper = _int_env("AZURE_OPENAI_MAX_COMPLETION_TOKENS_LIMIT") or default
        return min(desired, upper)

    async def chat_stream_async(self, messages, *, temperature: float = 0.0,
                                max_tokens: int | None = None):
        """메시지 목록을 보내고 답변을 글자 조각 단위로 받는다 (stream=True)."""
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            top_p=float(os.getenv("AZURE_OPENAI_TOP_P", "1.0")),
            frequency_penalty=float(os.getenv("AZURE_OPENAI_FREQUENCY_PENALTY", "0.0")),
            presence_penalty=float(os.getenv("AZURE_OPENAI_PRESENCE_PENALTY", "0.0")),
            max_completion_tokens=self._token_limit(max_tokens),
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


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
