"""/v1 요청 모델. 필드 의미는 API_CONTRACT.md 기준."""
from typing import Any, Literal

from pydantic import BaseModel


class ClassifyIn(BaseModel):
    text: str
    threshold: float | None = None


class BatchClassifyIn(BaseModel):
    texts: list[str]
    threshold: float | None = None


class AudioIn(BaseModel):
    kind: Literal["url", "base64"] = "url"  # base64 는 소용량 테스트용
    url: str | None = None
    data: str | None = None
    mime_type: str | None = None
    language: str | None = "ko-KR"


class SttIn(BaseModel):
    # transcript 가 이미 있으면(클라이언트측 STT) 바로 텍스트 흐름으로 진행
    provider: str | None = None
    language: str | None = "ko-KR"
    transcript: str | None = None
    confidence: float | None = None


class TtsIn(BaseModel):
    enabled: bool = False
    provider: str | None = None
    voice: str | None = None
    format: str | None = "mp3"
    speed: float | None = None


class LlmIn(BaseModel):
    # 서버측 상한(AZURE_OPENAI_MAX_COMPLETION_TOKENS_LIMIT)이 항상 우선
    max_completion_tokens: int | None = None
    temperature: float | None = None


class RespondIn(BaseModel):
    text: str | None = None
    session_id: str | None = None
    input_type: Literal["text", "audio", "transcript"] | None = None
    audio: AudioIn | None = None
    stt: SttIn | None = None
    tts: TtsIn | None = None
    llm: LlmIn | None = None
    client: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    def effective_text(self) -> str | None:
        text = (self.text or "").strip()
        if text:
            return text
        transcript = ((self.stt.transcript if self.stt else None) or "").strip()
        return transcript or None

    def input_meta(self) -> dict[str, Any]:
        return {
            "input_type": self.input_type or ("audio" if self.audio else "text"),
            "audio": self.audio.model_dump(exclude_none=True) if self.audio else None,
            "stt": self.stt.model_dump(exclude_none=True) if self.stt else None,
            "client": self.client,
            "metadata": self.metadata,
        }


class SessionCreateIn(BaseModel):
    session_id: str | None = None
