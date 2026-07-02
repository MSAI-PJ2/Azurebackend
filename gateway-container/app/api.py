"""[URL 목록] 이 서버가 받는 모든 요청 주소(엔드포인트)의 정의.

프론트엔드가 호출하는 주소와, 각 주소가 어떤 함수로 연결되는지가 여기 다 있다.
각 함수는 "요청을 받아서 → 알맞은 담당 모듈에 넘기는" 역할만 한다.
실제 상담 로직은 respond_flow.py, 외부 Azure 호출은 services/ 에 있다.

참고 — 함수 앞의 async: "비동기 함수"라는 뜻. 한 요청이 Azure 응답을 기다리는
동안에도 서버가 다른 요청을 처리할 수 있게 해 준다. await 는 "결과가 올 때까지
이 요청만 잠시 대기"라는 표시다.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from . import respond_flow
from .auth import current_user, require_api_key
from .contracts import BatchClassifyIn, ClassifyIn, RespondIn, SessionCreateIn
from .respond_flow import RespondRequestContext
from .services import services
from .session import session_repository

router = APIRouter()
# /v1/* 주소는 전부 인증을 거친다. Depends(...) = "이 함수를 먼저 통과해야 함"
# (require_api_key: x-api-key 헤더 검사 / current_user: 로그인 도입 자리 — auth.py)
v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key), Depends(current_user)])


@router.get("/healthz")
async def healthz():
    """서버 생존 확인용. Azure 가 주기적으로 호출해 서버가 살아있는지 본다."""
    return {"status": "ok"}


@v1.post("/classify")
async def classify(body: ClassifyIn):
    """문장 1개를 인지왜곡 분류기(cogdist)에 보내 라벨을 받는다."""
    return await services.classifier.classify_one(body.text, body.threshold)


@v1.post("/batch-classify")
async def batch_classify(body: BatchClassifyIn):
    """문장 여러 개를 한 번에 분류한다 (데이터 검증용)."""
    return await services.classifier.classify_batch(body.texts, body.threshold)


@v1.post("/respond")
async def respond(body: RespondIn):
    """상담 응답 생성 — 이 서비스의 핵심 주소.

    입력 형태(이미지/음성/텍스트/빈 입력)에 따라 네 가지 흐름 중 하나로 보낸다.
    응답은 한 번에 주지 않고 SSE 스트리밍(생성되는 대로 조각조각 전송)으로 보낸다
    — 그래서 반환값이 일반 JSON 이 아니라 StreamingResponse 다.
    """
    context = RespondRequestContext.from_body(body)  # 요청을 내부 형태로 정리

    if context.requires_ocr:
        # 채팅 캡쳐 이미지만 왔음 → OCR(Document Intelligence) 후 상담 흐름으로
        stream = respond_flow.ocr_then_respond_stream(
            context.session_id, context.input_meta, context.tts, context.llm)
    elif context.requires_stt:
        # 오디오만 왔음 → 먼저 음성→텍스트(STT) 변환 후 상담 흐름으로
        stream = respond_flow.stt_then_respond_stream(
            context.session_id, context.input_meta, context.tts, context.llm)
    elif not context.has_text:
        # 텍스트도 오디오도 없음 → "입력을 보내달라"는 안내만 반환
        stream = respond_flow.input_pending_stream(context.session_id, context.input_meta, context.tts)
    else:
        # 일반 텍스트 상담
        stream = respond_flow.respond_stream(
            context.text or "", context.session_id, context.input_meta, context.tts, context.llm)

    return StreamingResponse(stream, media_type="text/event-stream")


@v1.post("/sessions")
async def create_session(body: SessionCreateIn | None = None):
    """새 대화 세션(대화방)을 만든다. session_id 를 안 주면 서버가 발급."""
    return await session_repository.create(body.session_id if body else None)


@v1.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """세션의 저장된 대화 기록을 조회한다. 없으면 404."""
    state = await session_repository.snapshot(session_id)
    if state is None:
        raise HTTPException(404, "session not found")
    return state


router.include_router(v1)
