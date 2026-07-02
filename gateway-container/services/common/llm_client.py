"""Azure OpenAI Chat Completions 클라이언트 (async 스트리밍 전용).

필요 env: AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / AZURE_OPENAI_DEPLOYMENT.
토큰 상한: AZURE_OPENAI_MAX_COMPLETION_TOKENS(기본값이자 상한), *_LIMIT 로 상한 분리 가능.
"""
from __future__ import annotations

import os

from openai import AsyncAzureOpenAI


def _int_env(name: str) -> int | None:
    raw = os.getenv(name)
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


class LLMClient:
    def __init__(self):
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        missing = [n for n, v in {"AZURE_OPENAI_ENDPOINT": endpoint,
                                  "AZURE_OPENAI_API_KEY": api_key,
                                  "AZURE_OPENAI_DEPLOYMENT": deployment}.items() if not v]
        if missing:
            raise ValueError("Azure OpenAI missing env vars: " + ", ".join(missing))
        self.model = deployment
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
