"""[턴 빌더] 세션(DB)에 저장하는 대화 기록 한 건(턴)의 형태를 만드는 함수들.

role = 발화 주체("user" 또는 "assistant"), event = 어떤 상황의 기록인지.
프론트로 실시간 전송하는 SSE 이벤트(events.py)와는 별개 — 이쪽은 "보관용" 형식이다.
필드를 바꾸면 GET /v1/sessions 응답도 바뀌므로 API_CONTRACT.md 를 함께 갱신한다.
"""


def stt_failed_turn(input_meta: dict, result: dict, tts: dict | None) -> dict:
    """음성 인식 실패 기록 — 어떤 오디오가 왜 실패했는지 남긴다."""
    return {"role": "user", "text": "", "event": "stt_failed",
            "input": input_meta, "stt_result": result, "tts": tts}


def input_pending_turn(input_meta: dict, tts: dict | None) -> dict:
    """빈 입력 요청 기록."""
    return {"role": "user", "text": "", "event": "input_pending", "input": input_meta, "tts": tts}


def user_turn(text: str, primary: str, safety: dict, input_meta: dict, tts: dict | None) -> dict:
    """사용자 발화 기록 — 분류 라벨과 안전검사 결과를 함께 저장한다."""
    return {"role": "user", "text": text, "primary": primary,
            "safety": "safe" if safety.get("safe") else "blocked",
            "safety_reason": safety.get("reason"), "input": input_meta, "tts": tts}


def crisis_turn(payload: dict) -> dict:
    """위기 분기 기록 — AI 답변 대신 고정 위기 메시지가 나갔다는 표시(blocked=True)."""
    return {"role": "assistant", "text": payload.get("message", ""), "event": "crisis",
            "blocked": True, "reason": payload.get("reason")}


def assistant_turn(text: str, primary: str, chunks: list[dict], policy: dict | None = None) -> dict:
    """AI 답변 기록 — 어떤 참고자료(rag_chunk_ids)와 정책(policy)으로 생성했는지 남긴다."""
    turn = {"role": "assistant", "text": text, "event": "respond", "primary": primary,
            "rag_chunk_ids": [c["id"] for c in chunks]}
    if policy:
        turn["policy"] = policy  # 적용된 컨텍스트 정책 (orchestrator/context_policy.py)
    return turn
