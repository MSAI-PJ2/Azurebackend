"""위기 분기: LLM 을 우회하고 고정 메시지 + 핫라인 출력. 메시지/연락처는 여기서 수정."""

HOTLINES = [
    {"name": "자살예방상담전화", "phone": "1393", "hours": "24시간"},
    {"name": "정신건강위기상담전화", "phone": "1577-0199", "hours": "24시간"},
    {"name": "청소년전화", "phone": "1388", "hours": "24시간"},
]

CRISIS_MESSAGE = (
    "지금 많이 힘들고 고통스러우신 것 같아요. 무엇보다 당신의 안전이 가장 중요합니다. "
    "혼자 견디지 마시고, 아래 전문 상담 창구에 지금 연락해 주세요. 24시간 언제든 도움을 받을 수 있어요."
)


def lookup_regional_hotlines(region: str | None) -> list[dict]:
    """지역 유관기관 연락처 조회 — 미구현(전국 공통만 사용).

    ── [사람 작업 가이드] 위치 기반 유관기관 DB 조회 (도입 예정) ──────────
    1. 데이터: Cosmos 컨테이너(예: hotline-directory, PK=/region),
       문서 예 {"region":"서울특별시 강남구","name":"강남구 정신건강복지센터","phone":"02-...","hours":"평일 09-18시"}
    2. 입력: 프론트가 RespondIn.metadata.region 전달 → respond_flow 의 input_meta["metadata"] 로 접근
    3. 구현: 여기서 region 으로 조회해 list[dict] 반환. Cosmos SDK 는 블로킹이므로
       이 함수와 crisis_payload 를 async 로 바꾸고 asyncio.to_thread 사용, 호출부에 await.
       조회 실패/미등록 지역은 반드시 빈 리스트 반환 — 위기 응답은 어떤 경우에도 실패 금지.
    ────────────────────────────────────────────────────────────────
    """
    return []


def crisis_payload(reason: str | None = None, region: str | None = None) -> dict:
    return {
        "type": "crisis",
        "blocked": True,
        "reason": reason,
        "message": CRISIS_MESSAGE,
        "resources": [*lookup_regional_hotlines(region), *HOTLINES],
    }
