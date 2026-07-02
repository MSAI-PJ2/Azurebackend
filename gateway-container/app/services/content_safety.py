"""[안전검사 창구] 발화가 위험(자살/자해 등)한지 판정한다.

2단 구조:
    1차: Azure Content Safety (AI 기반 정밀 판정 — 설정돼 있을 때)
    2차: 키워드 검사 (Azure 가 꺼져 있거나 호출이 실패했을 때의 안전망)
반환 {safe, reason, source, ...} — source 필드로 "누가 판정했는지"를 항상 남긴다:
    content_safety(정상 경로) | keyword_fallback(Azure 실패로 대체) | keyword(Azure 비활성)
위기 판정이 조용히 누락되는 일이 없도록, 어떤 경우에도 반드시 판정 결과를 돌려준다.
"""
import logging

import httpx

from .. import settings

logger = logging.getLogger(__name__)

# 명백한 위기 신호 키워드 (공백 제거 후 부분일치로 검사)
_RISK_KEYWORDS = ("자살", "죽고싶", "자해", "끝내고싶", "사라지고싶",
                  "살이유가없", "살이유없", "목숨", "뛰어내리", "죽어버")

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    """HTTP 연결 재사용 (classifier.py 와 같은 패턴)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.CONTENT_SAFETY_TIMEOUT)
    return _client


def keyword_check(text: str) -> dict:
    """키워드 기반 검사 — 띄어쓰기를 없앤 문장에서 위험 키워드를 찾는다."""
    flat = text.replace(" ", "")
    matched = [k for k in _RISK_KEYWORDS if k in flat]
    if matched:
        return {"safe": False, "reason": "self_harm_signal", "matched": matched}
    return {"safe": True, "reason": None}


async def safety_check(text: str) -> dict:
    """Content Safety 가 설정돼 있으면 Azure 로 판정, 아니면 키워드 검사."""
    if settings.CONTENT_SAFETY_ENABLED and settings.CONTENT_SAFETY_ENDPOINT and settings.CONTENT_SAFETY_KEY:
        url = settings.CONTENT_SAFETY_ENDPOINT.rstrip("/") + "/contentsafety/text:analyze?api-version=2024-09-01"
        try:
            resp = await _http().post(url, json={"text": text},
                                      headers={"Ocp-Apim-Subscription-Key": settings.CONTENT_SAFETY_KEY})
            resp.raise_for_status()
            # Azure 응답: 카테고리(SelfHarm/Violence 등)별 위험 점수(severity)
            categories = {i["category"]: i["severity"] for i in resp.json().get("categoriesAnalysis", [])}
            # 기준값(THRESHOLD) 이상인 카테고리만 추린다
            flagged = {c: s for c, s in categories.items() if s >= settings.CONTENT_SAFETY_THRESHOLD}
            if flagged:
                # 자해가 있으면 self_harm, 아니면 가장 점수 높은 카테고리를 사유로
                reason = "self_harm" if "SelfHarm" in flagged else max(flagged, key=flagged.get).lower()
                return {"safe": False, "reason": reason, "categories": categories, "source": "content_safety"}
            return {"safe": True, "reason": None, "categories": categories, "source": "content_safety"}
        except Exception as exc:
            # Azure 호출 실패 → 키워드 검사로 대체하되, 대체했다는 사실을 로그와 응답에 남긴다
            logger.warning("Content Safety 호출 실패 — 키워드 fallback: %s", exc)
            return {**keyword_check(text), "source": "keyword_fallback", "cs_error": str(exc)[:140]}

    return {**keyword_check(text), "source": "keyword"}


class SafetyAdapter:
    async def check(self, text: str) -> dict:
        return await safety_check(text)
