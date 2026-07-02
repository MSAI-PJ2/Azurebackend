"""[인증] "이 요청을 처리해도 되는가"를 검사하는 곳. 현행 = x-api-key 헤더 검사.

api.py 의 모든 /v1 주소가 아래 두 함수를 통과해야 실행된다 (Depends 의존성).
로그인(Entra External ID) 도입 시에도 라우터는 그대로 두고 이 파일만 고치면 된다.
"""
from fastapi import Header, HTTPException

from . import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """임시 인증: 설정(API_KEY_REQUIRED=true)이 켜져 있으면 x-api-key 헤더를 검사.

    Header(default=None) = 요청 헤더에서 x-api-key 값을 꺼내 매개변수로 받는다는 뜻.
    키가 틀리면 401(인증 실패)을 던져서 요청 처리가 여기서 멈춘다.
    """
    if settings.API_KEY_REQUIRED and x_api_key != settings.API_KEY:
        raise HTTPException(401, "invalid api key")


async def current_user(authorization: str | None = Header(default=None)) -> str:
    """요청한 사용자가 누구인지(user_id)를 반환. 현재는 로그인이 없어 항상 "anonymous".

    ── [사람 작업 가이드] Microsoft Entra External ID(OIDC) 로그인 연동 ─────────
    흐름: 프론트가 Entra 로 로그인 → JWT(신원 증명 토큰) 발급 → 요청마다
          Authorization: Bearer <토큰> 첨부 → 이 함수가 토큰을 검증하고 user_id 추출.
    1. Entra 테넌트에 앱 등록 후 환경변수 준비:
         ENTRA_TENANT_ID   테넌트 GUID
         ENTRA_CLIENT_ID   이 API 앱 등록의 client id (토큰의 aud 와 일치해야 함)
         ENTRA_ISSUER      https://{테넌트GUID}.ciamlogin.com/{테넌트GUID}/v2.0
         ※ 서브도메인도 테넌트 '이름'이 아니라 GUID — 토큰의 iss 클레임과
           글자 단위로 같아야 검증을 통과한다.
    2. requirements.txt 에 PyJWT[crypto] 추가
    3. 이 함수에서:
       - authorization 헤더에서 "Bearer " 뒤의 토큰을 꺼낸다 (없으면 401)
       - 서명키(JWKS) 주소는 하드코딩하지 말고 OIDC 메타데이터에서 읽는다:
           GET {ENTRA_ISSUER}/.well-known/openid-configuration → 응답의 jwks_uri
         (issuer 뒤에 /discovery/v2.0/keys 를 그대로 붙이면 404 가 난다)
       - jwt.PyJWKClient(jwks_uri) 는 모듈 전역에 1회만 생성 (요청마다 생성 금지)
       - jwt.decode(token, key, algorithms=["RS256"],
                    audience=ENTRA_CLIENT_ID, issuer=ENTRA_ISSUER)
       - 검증 실패 → HTTPException(401) / 성공 → claims["oid"] 반환
    4. 환경변수 AUTH_MODE=entra 로 전환 — 라우터에 이미 의존성으로 걸려 있어서
       구현 전에는 아래 501 로 즉시 실패하고, 구현 후에는 자동으로 활성화된다.
       user_id 를 세션과 연결하려면 라우터에서 user_id: str = Depends(current_user) 로
       받아 오케스트레이터에 전달하고, 세션 저장/조회 조건에 포함시켜
       "내 세션만 접근"을 보장한다 (session/ 참고).
    5. require_api_key 는 서버 간 내부 호출용으로만 남기거나 제거.
    ─────────────────────────────────────────────────────────────────────
    """
    if settings.AUTH_MODE == "entra":
        # 구현 전에 실수로 entra 를 켜면 조용히 익명으로 동작하는 대신 명확히 실패시킨다
        raise HTTPException(501, "AUTH_MODE=entra is not implemented yet (see app/auth.py)")
    return "anonymous"
