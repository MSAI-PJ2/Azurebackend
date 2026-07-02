"""[LLM 통신] Azure OpenAI 에 실제로 접속해 답변을 스트리밍으로 받아오는 클라이언트.

app/services/llm.py(어댑터)가 이 클래스를 사용한다.
필요 환경변수: AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / AZURE_OPENAI_DEPLOYMENT.
토큰(답변 길이) 상한: AZURE_OPENAI_MAX_COMPLETION_TOKENS 가 기본값이자 상한이고,
더 높은 상한이 필요하면 *_LIMIT 로 분리해 지정한다.
"""
from __future__ import annotations

import os

from openai import AsyncAzureOpenAI


def _int_env(name: str) -> int | None:
    """환경변수를 정수로 읽는다. 없거나 숫자가 아니면 None."""
    raw = os.getenv(name)
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


class LLMClient:
    def __init__(self):
        # 필수 환경변수 3개 확인 — 빠진 게 있으면 이름을 알려주며 즉시 실패
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")  # Azure 에 배포한 모델 이름 (예: gpt-4.1-mini)
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
        """이번 요청의 답변 길이 상한을 결정한다.

        요청이 원하는 값(requested)을 쓰되, 서버 설정 상한(LIMIT)을 넘지 못하게 막는다
        — 한 요청이 지나치게 긴 답변을 시켜 비용/지연이 폭주하는 것을 방지.
        """
        default = _int_env("AZURE_OPENAI_MAX_COMPLETION_TOKENS") or fallback
        desired = max(1, requested) if requested else default
        upper = _int_env("AZURE_OPENAI_MAX_COMPLETION_TOKENS_LIMIT") or default
        return min(desired, upper)

    async def chat_stream_async(self, messages, *, temperature: float = 0.0,
                                max_tokens: int | None = None):
        """메시지 목록(시스템 프롬프트+대화)을 보내고, 답변을 글자 조각 단위로 받는다.

        stream=True 로 요청하면 Azure 가 완성을 기다리지 않고 생성되는 대로 조각(chunk)을
        보내 준다. 각 조각에서 새로 생성된 글자(delta.content)만 골라 yield 한다.
        """
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
