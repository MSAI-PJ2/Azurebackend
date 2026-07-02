"""게이트웨이 진입점 — 앱 생성/미들웨어/라우터 등록. 엔드포인트는 api.py, 흐름은 orchestrator/."""
import logging
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import settings
from .api import router

# App Insights — 연결 문자열이 있는 배포 환경에서만 활성화 (로컬은 없이 기동)
if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        configure_azure_monitor()
    except Exception as exc:  # 계측 실패가 기동을 막으면 안 된다
        logging.getLogger(__name__).warning("App Insights 초기화 실패(기동 계속): %s", exc)

app = FastAPI(title="mlnode-api-gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    return response


app.include_router(router)
