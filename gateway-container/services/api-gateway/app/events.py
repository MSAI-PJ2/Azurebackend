"""SSE 직렬화 + 클라이언트로 나가는 이벤트 payload. API_CONTRACT.md 와 1:1.

DB 저장 턴은 session/turns.py — 여기와 섞지 않는다.
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
    """payload dict 하나 → SSE data 프레임 하나."""
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def stt_processing_event(session_id: str, provider: str, language: str) -> dict:
    return {"type": "stt", "session_id": session_id, "status": "processing",
            "provider": provider, "language": language}


def stt_result_event(session_id: str, result: dict) -> dict:
    return {"type": "stt", "session_id": session_id, **result}


def input_required_event(session_id: str, reason: str, message: str) -> dict:
    return {"type": "input_required", "session_id": session_id, "reason": reason, "message": message}


def meta_event(session_id: str, turn_count: int, input_meta: dict, tts: dict | None,
               cls: dict | None = None) -> dict:
    payload = {"type": "meta", "session_id": session_id, "turn_count": turn_count,
               "input": input_meta, "tts": tts}
    if cls:
        payload.update({"primary": cls["primary"], "mode": cls["mode"], "labels": cls["labels"]})
    return payload


def chunks_event(session_id: str, chunks: list[dict]) -> dict:
    return {"type": "chunks", "session_id": session_id,
            "chunks": [{"id": c["id"], "content": c["content"]} for c in chunks]}


def token_event(session_id: str, text: str) -> dict:
    return {"type": "token", "session_id": session_id, "text": text}


def tts_event(session_id: str, tts_result: dict) -> dict:
    return {"type": "tts", "session_id": session_id, **tts_result}


def done_event(session_id: str) -> dict:
    return {"type": "done", "session_id": session_id}
