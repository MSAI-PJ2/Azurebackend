"""위험 발화 탐지: Azure Content Safety + 키워드 fallback.

반환 {safe, reason, source, ...} — source 로 판정 경로를 항상 드러낸다
(content_safety | keyword_fallback(Azure 실패) | keyword(비활성)).
"""
import logging

import httpx

from .. import settings

logger = logging.getLogger(__name__)

_RISK_KEYWORDS = ("자살", "죽고싶", "자해", "끝내고싶", "사라지고싶",
                  "살이유가없", "살이유없", "목숨", "뛰어내리", "죽어버")

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.CONTENT_SAFETY_TIMEOUT)
    return _client


def keyword_check(text: str) -> dict:
    flat = text.replace(" ", "")
    matched = [k for k in _RISK_KEYWORDS if k in flat]
    if matched:
        return {"safe": False, "reason": "self_harm_signal", "matched": matched}
    return {"safe": True, "reason": None}


async def safety_check(text: str) -> dict:
    if settings.CONTENT_SAFETY_ENABLED and settings.CONTENT_SAFETY_ENDPOINT and settings.CONTENT_SAFETY_KEY:
        url = settings.CONTENT_SAFETY_ENDPOINT.rstrip("/") + "/contentsafety/text:analyze?api-version=2024-09-01"
        try:
            resp = await _http().post(url, json={"text": text},
                                      headers={"Ocp-Apim-Subscription-Key": settings.CONTENT_SAFETY_KEY})
            resp.raise_for_status()
            categories = {i["category"]: i["severity"] for i in resp.json().get("categoriesAnalysis", [])}
            flagged = {c: s for c, s in categories.items() if s >= settings.CONTENT_SAFETY_THRESHOLD}
            if flagged:
                reason = "self_harm" if "SelfHarm" in flagged else max(flagged, key=flagged.get).lower()
                return {"safe": False, "reason": reason, "categories": categories, "source": "content_safety"}
            return {"safe": True, "reason": None, "categories": categories, "source": "content_safety"}
        except Exception as exc:
            logger.warning("Content Safety 호출 실패 — 키워드 fallback: %s", exc)
            return {**keyword_check(text), "source": "keyword_fallback", "cs_error": str(exc)[:140]}

    return {**keyword_check(text), "source": "keyword"}


class SafetyAdapter:
    async def check(self, text: str) -> dict:
        return await safety_check(text)
