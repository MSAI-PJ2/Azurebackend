"""환경변수 설정. 새 항목은 .env.example 에도 기록한다."""
import os


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in ("true", "1")


# 분류기 (내부 cogdist Container App)
KLUE_API_URL = os.getenv("KLUE_API_URL", "http://cogdist:8000")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

# 인증 / CORS — AUTH_MODE: api_key(현행) | entra(도입 예정, auth.py 가이드)
API_KEY = os.getenv("API_KEY", "")
API_KEY_REQUIRED = _bool("API_KEY_REQUIRED", False)
AUTH_MODE = os.getenv("AUTH_MODE", "api_key").strip().lower()
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
    if origin.strip()
]

# Azure Content Safety
CONTENT_SAFETY_ENABLED = _bool("CONTENT_SAFETY_ENABLED", False)
CONTENT_SAFETY_ENDPOINT = os.getenv("CONTENT_SAFETY_ENDPOINT", "")
CONTENT_SAFETY_KEY = os.getenv("CONTENT_SAFETY_KEY", "")
CONTENT_SAFETY_THRESHOLD = int(os.getenv("CONTENT_SAFETY_THRESHOLD", "2"))  # severity 0/2/4/6
CONTENT_SAFETY_TIMEOUT = float(os.getenv("CONTENT_SAFETY_TIMEOUT", "5"))

# RAG
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "4"))

# 세션 저장소 — memory(개발/테스트) | cosmos(운영)
SESSION_REPOSITORY = os.getenv("SESSION_REPOSITORY", "memory")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
SESSION_MAX_TURNS = int(os.getenv("SESSION_MAX_TURNS", "20"))
SESSION_CONTEXT_TURNS = int(os.getenv("SESSION_CONTEXT_TURNS", "6"))
