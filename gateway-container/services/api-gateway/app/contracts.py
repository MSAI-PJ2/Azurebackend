"""[요청 형식] 프론트엔드가 보내는 JSON 의 모양(스키마) 정의.

Pydantic 모델 = "이 요청에는 이런 이름/타입의 필드가 온다"는 선언.
FastAPI 가 요청 JSON 을 자동으로 검사해서, 형식이 틀리면 코드 실행 전에
422 오류를 돌려준다. `str | None = None` 은 "문자열 또는 생략 가능(기본 None)".
필드의 자세한 의미는 API_CONTRACT.md 가 기준 문서다.
"""
from typing import Any, Literal

from pydantic import BaseModel


class ClassifyIn(BaseModel):
    """POST /v1/classify 의 입력."""
    text: str
    threshold: float | None = None  # 분류 확신 기준값 (생략 시 모델 기본값)


class BatchClassifyIn(BaseModel):
    """POST /v1/batch-classify 의 입력 — 문장 여러 개."""
    texts: list[str]
    threshold: float | None = None


class AudioIn(BaseModel):
    """음성 입력. kind 가 base64 면 data 에, url 이면 url 에 오디오가 담긴다."""
    kind: Literal["url", "base64"] = "url"  # base64 는 소용량 테스트용
    url: str | None = None
    data: str | None = None                 # base64 로 인코딩된 오디오 바이트
    mime_type: str | None = None            # 예: audio/webm, audio/wav
    language: str | None = "ko-KR"


class SttIn(BaseModel):
    """음성→텍스트 관련 정보. transcript(전사문)가 이미 있으면 STT 를 건너뛴다."""
    provider: str | None = None
    language: str | None = "ko-KR"
    transcript: str | None = None
    confidence: float | None = None


class TtsIn(BaseModel):
    """텍스트→음성 옵션. enabled=true 면 답변을 음성으로도 합성해 준다."""
    enabled: bool = False
    provider: str | None = None
    voice: str | None = None      # 예: ko-KR-SunHiNeural
    format: str | None = "mp3"
    speed: float | None = None


class LlmIn(BaseModel):
    """요청 단위 LLM 옵션. 서버측 상한(AZURE_OPENAI_MAX_COMPLETION_TOKENS_LIMIT)이 항상 우선."""
    max_completion_tokens: int | None = None  # 답변 최대 길이(토큰)
    temperature: float | None = None          # 높을수록 답변이 다양/무작위


class RespondIn(BaseModel):
    """POST /v1/respond 의 입력 — 텍스트/음성/전사문 중 하나로 상담을 요청한다."""
    text: str | None = None
    session_id: str | None = None   # 대화방 ID. 같은 ID 로 보내면 대화가 이어진다
    input_type: Literal["text", "audio", "transcript"] | None = None
    audio: AudioIn | None = None
    stt: SttIn | None = None
    tts: TtsIn | None = None
    llm: LlmIn | None = None
    client: dict[str, Any] | None = None    # 프론트가 넣는 자유 필드 (그대로 저장됨)
    metadata: dict[str, Any] | None = None

    def effective_text(self) -> str | None:
        """실제 처리할 텍스트를 고른다: text 가 있으면 text, 없으면 stt.transcript."""
        text = (self.text or "").strip()
        if text:
            return text
        transcript = ((self.stt.transcript if self.stt else None) or "").strip()
        return transcript or None

    def input_meta(self) -> dict[str, Any]:
        """어떤 형태의 입력이었는지 기록용으로 정리 (세션 저장·meta 이벤트에 들어감)."""
        return {
            "input_type": self.input_type or ("audio" if self.audio else "text"),
            "audio": self.audio.model_dump(exclude_none=True) if self.audio else None,
            "stt": self.stt.model_dump(exclude_none=True) if self.stt else None,
            "client": self.client,
            "metadata": self.metadata,
        }


class SessionCreateIn(BaseModel):
    """POST /v1/sessions 의 입력. session_id 생략 시 서버가 발급."""
    session_id: str | None = None
