"""인증 경계. 현행 = x-api-key. 모든 v1 라우터가 require_api_key + current_user 를 의존성으로 쓴다."""
from fastapi import Header, HTTPException

from . import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.API_KEY_REQUIRED and x_api_key != settings.API_KEY:
        raise HTTPException(401, "invalid api key")


async def current_user(authorization: str | None = Header(default=None)) -> str:
    """요청의 user_id 반환. 현재 익명 — Entra External ID 도입 시 이 함수만 구현하면 된다.

    ── [사람 작업 가이드] Microsoft Entra External ID(OIDC) ─────────────────
    흐름: 프론트 OIDC 로그인 → JWT → Authorization: Bearer 첨부 → 여기서 검증 → user_id.
    1. 앱 등록 후 env: ENTRA_TENANT_ID(GUID), ENTRA_CLIENT_ID(=aud),
       ENTRA_ISSUER=https://{테넌트GUID}.ciamlogin.com/{테넌트GUID}/v2.0
       (서브도메인도 GUID — 토큰 iss 클레임과 글자 단위 일치해야 함)
    2. requirements.txt 에 PyJWT[crypto] 추가
    3. Bearer 토큰 파싱(없으면 401) → jwks_uri 는 하드코딩 금지,
       GET {ENTRA_ISSUER}/.well-known/openid-configuration 의 jwks_uri 사용
       (issuer 뒤에 /discovery/v2.0/keys 를 그대로 붙이면 404)
       → jwt.PyJWKClient(jwks_uri) 는 모듈 전역 1회 생성
       → jwt.decode(token, key, algorithms=["RS256"], audience=ENTRA_CLIENT_ID,
                    issuer=ENTRA_ISSUER) → 실패 시 401 → claims["oid"] 반환
    4. AUTH_MODE=entra 전환 — 라우터에 이미 의존성으로 걸려 있어 자동 활성화.
       세션 문서 저장/조회에 user_id 를 포함해 "내 세션만 접근" 보장 (session/ 참고)
    ─────────────────────────────────────────────────────────────────────
    """
    if settings.AUTH_MODE == "entra":
        raise HTTPException(501, "AUTH_MODE=entra is not implemented yet (see app/auth.py)")
    return "anonymous"
