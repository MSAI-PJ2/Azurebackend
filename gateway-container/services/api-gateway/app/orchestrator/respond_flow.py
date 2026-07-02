"""/v1/respond 오케스트레이션.

respond_stream 한 턴: 세션 로드 → safety/classify/retrieve 병렬 → 정책 결정
→ (위기면 고정 메시지 후 종료) → RAG 재정렬 → 프롬프트 → LLM 스트리밍
→ (옵션) TTS → 세션 저장 → done.
"""
import asyncio

from ..events import (
    INPUT_REQUIRED_STT_MESSAGE, INPUT_REQUIRED_TEXT_MESSAGE,
    chunks_event, done_event, input_required_event, meta_event, sse,
    stt_processing_event, stt_result_event, token_event, tts_event,
)
from ..prompts import build_llm_messages
from ..ranking import rerank
from ..services import services
from ..session import session_repository
from ..session.turns import assistant_turn, crisis_turn, input_pending_turn, stt_failed_turn, user_turn
from . import context_policy, crisis
from .request_context import RespondRequestContext, default_text_input_meta


async def stt_then_respond_stream(session_id=None, input_meta=None, tts=None, llm=None):
    """오디오 입력: STT → stt 이벤트 → 성공 시 respond_stream 으로 계속."""
    context = RespondRequestContext(session_id, None, input_meta or {}, tts, llm)
    session = await session_repository.ensure(context.session_id)
    session_id = session["session_id"]
    context = RespondRequestContext(session_id, None, context.input_meta, tts, llm)

    yield sse(stt_processing_event(session_id, context.stt_provider, context.language))
    result = await services.speech.transcribe_audio(context.audio)

    if result.get("status") != "completed" or not result.get("transcript"):
        # STT 실패는 조용히 넘어가지 않는다 — 실패 이벤트 + 재입력 요청을 명시적으로 전송
        await session_repository.append_turn(session_id, stt_failed_turn(context.input_meta, result, tts))
        yield sse(stt_result_event(session_id, result))
        yield sse(input_required_event(session_id, result.get("status") or "stt_failed",
                                       INPUT_REQUIRED_STT_MESSAGE))
        yield sse(done_event(session_id))
        return

    context = context.with_transcript(result)
    yield sse(stt_result_event(session_id, result))
    async for event in respond_stream(context.text or "", session_id, context.input_meta, tts, llm):
        yield event


async def input_pending_stream(session_id=None, input_meta=None, tts=None):
    """텍스트도 오디오도 없는 요청: 입력 요청 이벤트만 보내고 종료."""
    session = await session_repository.ensure(session_id)
    session_id = session["session_id"]
    input_meta = input_meta or {}
    await session_repository.append_turn(session_id, input_pending_turn(input_meta, tts))
    snap = await session_repository.snapshot(session_id)

    yield sse(meta_event(session_id, snap["turn_count"], input_meta, tts))
    yield sse(input_required_event(session_id, "text_required", INPUT_REQUIRED_TEXT_MESSAGE))
    yield sse(done_event(session_id))


async def respond_stream(text: str, session_id=None, input_meta=None, tts=None, llm=None):
    session = await session_repository.ensure(session_id)
    session_id = session["session_id"]
    prior_messages = await session_repository.recent_llm_messages(session_id)
    input_meta = default_text_input_meta(input_meta)

    safety, cls, cands = await asyncio.gather(
        services.safety.check(text),
        services.classifier.classify_one(text),
        services.retriever.retrieve(text),
    )
    primary = cls["primary"]
    confidence = max((l["score"] for l in cls["labels"] if l["label"] == primary), default=0.0)
    policy = context_policy.resolve(safety, cls)

    await session_repository.append_turn(session_id, user_turn(text, primary, safety, input_meta, tts))
    snap = await session_repository.snapshot(session_id)
    yield sse(meta_event(session_id, snap["turn_count"], input_meta, tts, cls))

    if policy.is_crisis:
        payload = crisis.crisis_payload(reason=safety.get("reason"))
        yield sse(payload)
        await session_repository.append_turn(session_id, crisis_turn(payload))
        if tts and tts.get("enabled"):
            yield sse(tts_event(session_id, await services.speech.synthesize_tts(payload.get("message", ""), tts)))
        yield sse(done_event(session_id))
        return

    chunks = rerank(cands, primary, confidence, top_n=policy.rag_top_n) if policy.use_rag else []
    yield sse(chunks_event(session_id, chunks))

    messages = build_llm_messages(policy.prompt_strategy, primary, chunks, prior_messages, text)
    assistant_parts: list[str] = []
    async for tok in services.llm.chat_stream_async(messages, llm):
        assistant_parts.append(tok)
        yield sse(token_event(session_id, tok))

    assistant_text = "".join(assistant_parts).strip()
    if assistant_text:
        await session_repository.append_turn(
            session_id, assistant_turn(assistant_text, primary, chunks, policy=policy.as_metadata()))

    # TTS 는 완성 문장으로 합성하므로 스트리밍 종료 후 수행
    if tts and tts.get("enabled"):
        yield sse(tts_event(session_id, await services.speech.synthesize_tts(assistant_text, tts)))

    yield sse(done_event(session_id))
