"""v1 라우터 전체. HTTP 만 담당 — 흐름은 orchestrator/, 외부 호출은 services/."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .auth import current_user, require_api_key
from .contracts import BatchClassifyIn, ClassifyIn, RespondIn, SessionCreateIn
from .orchestrator import respond_flow
from .orchestrator.request_context import RespondRequestContext
from .services import services
from .session import session_repository

router = APIRouter()
v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key), Depends(current_user)])


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@v1.post("/classify")
async def classify(body: ClassifyIn):
    return await services.classifier.classify_one(body.text, body.threshold)


@v1.post("/batch-classify")
async def batch_classify(body: BatchClassifyIn):
    return await services.classifier.classify_batch(body.texts, body.threshold)


@v1.post("/respond")
async def respond(body: RespondIn):
    context = RespondRequestContext.from_body(body)

    if context.requires_stt:
        # STT 를 스트리밍 안에서 수행해 stt 이벤트(processing/completed/error)를 그대로 전달
        stream = respond_flow.stt_then_respond_stream(
            context.session_id, context.input_meta, context.tts, context.llm)
    elif not context.has_text:
        stream = respond_flow.input_pending_stream(context.session_id, context.input_meta, context.tts)
    else:
        stream = respond_flow.respond_stream(
            context.text or "", context.session_id, context.input_meta, context.tts, context.llm)

    return StreamingResponse(stream, media_type="text/event-stream")


@v1.post("/sessions")
async def create_session(body: SessionCreateIn | None = None):
    return await session_repository.create(body.session_id if body else None)


@v1.get("/sessions/{session_id}")
async def get_session(session_id: str):
    state = await session_repository.snapshot(session_id)
    if state is None:
        raise HTTPException(404, "session not found")
    return state


router.include_router(v1)
