"""게이트웨이 인증 경계.

현행(운영): x-api-key 헤더 검사 (AUTH_MODE=api_key, 기본값).
도입 예정: Microsoft Entra External ID (OIDC) — 아래 [사람 작업 가이드] 참고.

모든 v1 라우터가 require_api_key 와 current_user 를 의존성으로 사용한다
(api/v1/*.py 의 APIRouter(dependencies=...)). 인증 방식이 바뀌어도
라우터 코드는 수정할 필요가 없도록 이 모듈 안에서만 구현을 바꾼다.
"""
from fastapi import Header, HTTPException

from . import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """현행 임시 인증: API_KEY_REQUIRED=true 이면 x-api-key 헤더를 검사한다."""
    if settings.API_KEY_REQUIRED and x_api_key != settings.API_KEY:
        raise HTTPException(401, "invalid api key")


async def current_user(authorization: str | None = Header(default=None)) -> str:
    """요청의 사용자 식별자(user_id)를 반환한다.

    현재는 로그인 없이 익명("anonymous")으로 동작하고, 세션은 클라이언트가 보내는
    session_id 로만 구분된다. Entra External ID 도입 시 이 함수가 JWT 에서
    user_id 를 추출하는 유일한 지점이 된다 (라우터/오케스트레이터는 그대로).

    ── [사람 작업 가이드] Microsoft Entra External ID(OIDC) 로그인 연동 ──────────
    전체 흐름 (I/O 다이어그램 "로그인·Identity" 참고):
      프론트가 Entra External ID 로 OIDC 로그인 → JWT(access token) 발급
      → 요청마다 Authorization: Bearer <token> 첨부
      → 게이트웨이가 토큰 검증(JWKS) 후 user_id 추출 → 세션을 user_id 로 스코프

    구현 순서:
      1. Entra External ID 테넌트에 앱 등록(SPA + API) 후 아래 환경변수 준비
           ENTRA_TENANT_ID       테넌트 GUID
           ENTRA_CLIENT_ID       (이 API 를 나타내는 앱 등록의 client id = aud)
           ENTRA_ISSUER          https://{ENTRA_TENANT_ID}.ciamlogin.com/{ENTRA_TENANT_ID}/v2.0
             주의: 서브도메인도 테넌트 '이름'이 아니라 테넌트 GUID 다. 실제 발급 토큰의
             iss 클레임과 글자 단위로 일치해야 jwt.decode 의 issuer 검증을 통과한다.
      2. requirements.txt 에 PyJWT[crypto] (또는 python-jose) 추가
      3. 이 함수에서:
           - Authorization 헤더에서 Bearer 토큰 파싱 (없으면 401)
           - JWKS 주소는 하드코딩하지 말고 OIDC 메타데이터에서 읽는다:
               GET f"{ENTRA_ISSUER}/.well-known/openid-configuration" → json()["jwks_uri"]
             (형태는 https://{tenant-id}.ciamlogin.com/{tenant-id}/discovery/v2.0/keys —
              issuer 끝의 /v2.0 이 빠진 경로다. issuer 뒤에 그대로 이어붙이면 404)
           - jwt.PyJWKClient(jwks_uri) 는 모듈 전역에 1회 생성 — 요청마다 만들지 말 것
           - jwt.decode(token, key, algorithms=["RS256"],
                        audience=ENTRA_CLIENT_ID, issuer=ENTRA_ISSUER)
           - 검증 실패 → HTTPException(401)
           - user_id = claims["oid"] (또는 "sub") 반환
      4. AUTH_MODE=entra 로 전환. 라우터에는 이미 current_user 가 의존성으로 걸려 있어
         (api/v1/*.py) 구현 전에는 501 로 fail-fast 하고, 구현 후에는 자동 활성화된다.
         user_id 값을 세션에 연결하려면 라우터에서 user_id: str = Depends(current_user) 로
         받아 오케스트레이터에 전달하고, 세션 문서 저장/조회 조건에 user_id 를 포함해
         "내 세션만 접근" 을 보장한다 (session/ 참고).
      5. require_api_key 는 서버-서버 내부 호출용으로만 남기거나 제거
    ──────────────────────────────────────────────────────────────────────────
    """
    if settings.AUTH_MODE == "entra":
        # 위 가이드 구현 전까지는 명시적으로 실패시켜 설정 실수를 조기에 드러낸다.
        raise HTTPException(501, "AUTH_MODE=entra is not implemented yet (see core/auth.py)")
    return "anonymous"
