"""[위기 대응] 위험(자살/자해) 발화가 감지됐을 때의 고정 응답.

이때는 AI(LLM)에게 답변을 맡기지 않는다 — 잘못된 생성 답변의 위험을 없애기 위해
사람이 미리 써 둔 메시지와 전문 상담 핫라인을 그대로 내보낸다.
메시지 문구와 연락처를 바꾸려면 아래 CRISIS_MESSAGE / HOTLINES 만 수정하면 된다.
"""

# 24시간 전국 공통 위기 상담 창구 (지역별 창구는 아래 가이드 참고)
HOTLINES = [
    {"name": "자살예방상담전화", "phone": "1393", "hours": "24시간"},
    {"name": "정신건강위기상담전화", "phone": "1577-0199", "hours": "24시간"},
    {"name": "청소년전화", "phone": "1388", "hours": "24시간"},
]

# 위험 감지 시 그대로 출력되는 고정 메시지 (운영 정책에 맞게 수정)
CRISIS_MESSAGE = (
    "지금 많이 힘들고 고통스러우신 것 같아요. 무엇보다 당신의 안전이 가장 중요합니다. "
    "혼자 견디지 마시고, 아래 전문 상담 창구에 지금 연락해 주세요. 24시간 언제든 도움을 받을 수 있어요."
)


def lookup_regional_hotlines(region: str | None) -> list[dict]:
    """내담자 지역의 상담기관 조회 — 아직 미구현이라 항상 빈 목록(전국 공통만 노출).

    ── [사람 작업 가이드] 위치 기반 유관기관 DB 조회 (도입 예정) ──────────
    목표: 내담자 지역의 정신건강복지센터를 전국 공통 창구보다 먼저 보여주기.
    1. 데이터: Cosmos DB 에 연락처 컨테이너 생성 (예: hotline-directory, 파티션키 /region)
       문서 예 {"region":"서울특별시 강남구","name":"강남구 정신건강복지센터",
                "phone":"02-...","hours":"평일 09-18시"}
    2. 입력: 프론트가 요청의 metadata.region 에 지역명을 넣어 보낸다
       → respond_stream 에서 input_meta["metadata"] 로 꺼낼 수 있다
    3. 구현: 이 함수에서 region 으로 Cosmos 를 조회해 목록 반환.
       Cosmos SDK 는 블로킹(기다리는 동안 서버가 멈춤)이므로 session/cosmos_repository.py
       처럼 asyncio.to_thread 로 감싸고, 이 함수와 crisis_payload 를 async 로 바꾼 뒤
       respond_stream 의 호출부에 await 를 붙인다.
    4. 안전: 조회 실패·미등록 지역이면 반드시 빈 목록을 반환할 것 —
       위기 응답은 어떤 경우에도 실패하면 안 된다 (전국 공통 창구가 항상 나가야 함).
    ────────────────────────────────────────────────────────────────
    """
    return []


def crisis_payload(reason: str | None = None, region: str | None = None) -> dict:
    """프론트로 보낼 위기 이벤트 한 덩어리 (respond_stream 이 LLM 대신 이것을 출력)."""
    return {
        "type": "crisis",
        "blocked": True,          # 이 턴은 AI 답변이 차단됐다는 표시
        "reason": reason,         # 차단 사유 (예: self_harm_signal)
        "message": CRISIS_MESSAGE,
        "resources": [*lookup_regional_hotlines(region), *HOTLINES],  # 지역 창구 먼저, 전국 공통 다음
    }
