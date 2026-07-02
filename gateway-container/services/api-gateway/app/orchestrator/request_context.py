"""[요청 정리] /v1/respond 로 들어온 요청을 내부에서 다루기 쉬운 형태로 바꾼다.

"이 요청이 텍스트인가, 음성인가, 아무것도 없는가" 같은 판단을 respond_flow 밖으로
분리해 둔 것. api.py 가 요청을 받자마자 from_body() 로 이 객체를 만들고,
requires_stt / has_text 로 어느 흐름으로 보낼지 결정한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import RespondIn

DEFAULT_LANGUAGE = "ko-KR"


@dataclass(frozen=True)  # 읽기 전용 데이터 묶음 — 흐름 중간에 값이 바뀌는 실수를 막는다
class RespondRequestContext:
    session_id: str | None
    text: str | None               # 실제 처리할 텍스트 (text 또는 stt.transcript 에서 온 것)
    input_meta: dict[str, Any]     # 입력 형태 기록 (세션 저장·meta 이벤트용)
    tts: dict[str, Any] | None = None
    llm: dict[str, Any] | None = None

    @classmethod
    def from_body(cls, body: RespondIn) -> "RespondRequestContext":
        """프론트 요청(RespondIn) → 내부 컨텍스트로 변환."""
        return cls(
            session_id=body.session_id,
            text=body.effective_text(),
            input_meta=body.input_meta(),
            tts=body.tts.model_dump(exclude_none=True) if body.tts else None,
            llm=body.llm.model_dump(exclude_none=True) if body.llm else None,
        )

    # @property = 함수를 변수처럼 읽게 해 주는 문법 (context.has_text 처럼 괄호 없이 사용)

    @property
    def has_text(self) -> bool:
        """처리할 텍스트가 있는가?"""
        return bool((self.text or "").strip())

    @property
    def requires_stt(self) -> bool:
        """오디오만 있고 텍스트가 없어서 음성 인식(STT)이 먼저 필요한가?"""
        return bool(self.input_meta.get("audio")) and not self.has_text

    @property
    def requires_ocr(self) -> bool:
        """채팅 캡쳐 이미지만 있고 텍스트가 없어서 OCR 이 먼저 필요한가?"""
        return bool(self.input_meta.get("image")) and not self.has_text

    @property
    def audio(self) -> dict[str, Any]:
        return dict(self.input_meta.get("audio") or {})

    @property
    def image(self) -> dict[str, Any]:
        return dict(self.input_meta.get("image") or {})

    @property
    def sender_names(self) -> list[str]:
        """OCR 화자 판별 보정용 상대 이름 목록 (요청의 ocr.sender_names)."""
        return list((self.input_meta.get("ocr") or {}).get("sender_names") or [])

    @property
    def language(self) -> str:
        """인식 언어: stt.language > audio.language > 기본값(ko-KR) 순서로 고른다."""
        stt = self.input_meta.get("stt") or {}
        return stt.get("language") or self.audio.get("language") or DEFAULT_LANGUAGE

    @property
    def stt_provider(self) -> str:
        return (self.input_meta.get("stt") or {}).get("provider") or "azure"

    def with_transcript(self, result: dict[str, Any]) -> "RespondRequestContext":
        """STT 성공 후: 전사문을 text 로 넣고 input_type 을 transcript 로 바꾼 새 컨텍스트."""
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
    """input_meta 없이 호출된 경우(내부 호출 등)의 기본 형태."""
    return input_meta or {"input_type": "text"}
