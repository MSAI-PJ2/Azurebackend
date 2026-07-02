"""/v1/respond 요청 정규화 — 입력 형태(text/transcript/audio) 판단을 흐름 밖으로 분리."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import RespondIn

DEFAULT_LANGUAGE = "ko-KR"


@dataclass(frozen=True)
class RespondRequestContext:
    session_id: str | None
    text: str | None
    input_meta: dict[str, Any]
    tts: dict[str, Any] | None = None
    llm: dict[str, Any] | None = None

    @classmethod
    def from_body(cls, body: RespondIn) -> "RespondRequestContext":
        return cls(
            session_id=body.session_id,
            text=body.effective_text(),
            input_meta=body.input_meta(),
            tts=body.tts.model_dump(exclude_none=True) if body.tts else None,
            llm=body.llm.model_dump(exclude_none=True) if body.llm else None,
        )

    @property
    def has_text(self) -> bool:
        return bool((self.text or "").strip())

    @property
    def requires_stt(self) -> bool:
        return bool(self.input_meta.get("audio")) and not self.has_text

    @property
    def audio(self) -> dict[str, Any]:
        return dict(self.input_meta.get("audio") or {})

    @property
    def language(self) -> str:
        stt = self.input_meta.get("stt") or {}
        return stt.get("language") or self.audio.get("language") or DEFAULT_LANGUAGE

    @property
    def stt_provider(self) -> str:
        return (self.input_meta.get("stt") or {}).get("provider") or "azure"

    def with_transcript(self, result: dict[str, Any]) -> "RespondRequestContext":
        """STT 성공 결과를 반영한 새 컨텍스트."""
        input_meta = {
            **self.input_meta,
            "input_type": "transcript",
            "stt": {
                **(self.input_meta.get("stt") or {}),
                "provider": result.get("provider"),
                "language": result.get("language") or self.language,
                "transcript": result.get("transcript"),
                "confidence": result.get("confidence"),
                "recognition_status": result.get("recognition_status"),
            },
        }
        return RespondRequestContext(self.session_id, result.get("transcript"),
                                     input_meta, self.tts, self.llm)


def default_text_input_meta(input_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return input_meta or {"input_type": "text"}
