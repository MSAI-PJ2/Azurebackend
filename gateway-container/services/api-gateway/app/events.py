"""[SSE 이벤트] 스트리밍으로 프론트엔드에 보내는 메시지 조각들의 형식.

SSE(Server-Sent Events) = 서버가 응답을 끊지 않고 "data: {...}" 줄을 계속
흘려보내는 방식. 프론트는 도착하는 이벤트를 type 필드로 구분해 화면에 반영한다.
    meta(분류 결과) → chunks(참고자료) → token(답변 글자들) → done(끝)
이벤트의 종류/필드는 API_CONTRACT.md 와 1:1 — 여기를 바꾸면 프론트도 바꿔야 한다.
DB 에 저장하는 대화 기록은 session/turns.py — 역할이 다르므로 섞지 않는다.
"""
import json

INPUT_REQUIRED_STT_MESSAGE = (
    "audio payload was accepted, but STT did not produce a transcript. "
    "Check stt event error/reason, or send text/stt.transcript."
)
INPUT_REQUIRED_TEXT_MESSAGE = (
    "No text or transcript was provided. Send text, stt.transcript, or an audio payload."
)


def sse(obj: dict) -> str:
    """dict 하나를 SSE 한 프레임("data: {...}\\n\\n")으로 직렬화한다."""
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def stt_processing_event(session_id: str, provider: str, language: str) -> dict:
    """"음성 인식을 시작했다"는 알림 — 프론트가 로딩 표시를 띄울 수 있게."""
    return {"type": "stt", "session_id": session_id, "status": "processing",
            "provider": provider, "language": language}


def stt_result_event(session_id: str, result: dict) -> dict:
    """음성 인식 결과 (성공: transcript 포함 / 실패: error·reason 포함)."""
    return {"type": "stt", "session_id": session_id, **result}


def input_required_event(session_id: str, reason: str, message: str) -> dict:
    """처리할 입력이 없거나 STT 실패 — 사용자에게 재입력을 요청한다."""
    return {"type": "input_required", "session_id": session_id, "reason": reason, "message": message}


def meta_event(session_id: str, turn_count: int, input_meta: dict, tts: dict | None,
               cls: dict | None = None) -> dict:
    """턴 시작 정보: 몇 번째 턴인지 + 인지왜곡 분류 결과(primary/labels)."""
    payload = {"type": "meta", "session_id": session_id, "turn_count": turn_count,
               "input": input_meta, "tts": tts}
    if cls:
        payload.update({"primary": cls["primary"], "mode": cls["mode"], "labels": cls["labels"]})
    return payload


def chunks_event(session_id: str, chunks: list[dict]) -> dict:
    """RAG 로 검색된 참고자료 목록 (id 와 본문만 추려서 전달)."""
    return {"type": "chunks", "session_id": session_id,
            "chunks": [{"id": c["id"], "content": c["content"]} for c in chunks]}


def token_event(session_id: str, text: str) -> dict:
    """LLM 이 생성한 답변 조각 — 이 이벤트들을 이어붙이면 전체 답변이 된다."""
    return {"type": "token", "session_id": session_id, "text": text}


def tts_event(session_id: str, tts_result: dict) -> dict:
    """합성된 음성 (base64 오디오 포함) 또는 합성 실패 정보."""
    return {"type": "tts", "session_id": session_id, **tts_result}


def done_event(session_id: str) -> dict:
    """이 턴의 스트리밍이 끝났다는 신호 — 항상 마지막 이벤트."""
    return {"type": "done", "session_id": session_id}
