"""인지왜곡 분류기(cogdist Container App) 클라이언트.

응답 계약(strict): {text, mode, model, model_version, threshold, primary,
labels:[{label, score, selected}]}. 계약 밖 응답은 오류다 — 분류기를 고친다.
"""
from typing import Any

import httpx

from .. import settings

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    # 커넥션 풀 재사용 (요청마다 생성하면 TLS 핸드셰이크 낭비)
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS)
    return _client


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_result(data: dict[str, Any], *, fallback_text: str = "",
                 threshold: float | None = None) -> dict[str, Any]:
    """strict 파서: primary 와 labels[{label,score,selected}] 필수."""
    if not isinstance(data, dict) or "primary" not in data:
        raise ValueError("classifier response missing 'primary'")
    if not isinstance(data.get("labels"), list) or not data["labels"]:
        raise ValueError("classifier response missing 'labels'")

    labels = [
        {"label": str(item["label"]),
         "score": round(_as_float(item.get("score", 1.0), 1.0), 4),
         "selected": bool(item.get("selected", False))}
        for item in data["labels"]
    ]
    return {
        "text": str(data.get("text") or fallback_text or ""),
        "mode": str(data.get("mode") or "single"),
        "model": str(data.get("model") or "unknown"),
        "model_version": str(data.get("model_version") or "unknown"),
        "threshold": _as_float(data.get("threshold", threshold if threshold is not None else 0.5), 0.5),
        "primary": str(data["primary"]),
        "labels": labels,
    }


class ClassifierAdapter:
    async def classify_one(self, text: str, threshold: float | None = None) -> dict:
        response = await _http().post(f"{settings.KLUE_API_URL}/v1/predict",
                                      json={"text": text, "threshold": threshold})
        response.raise_for_status()
        return parse_result(response.json(), fallback_text=text, threshold=threshold)

    async def classify_batch(self, texts: list[str], threshold: float | None = None) -> dict:
        response = await _http().post(f"{settings.KLUE_API_URL}/v1/batch-predict",
                                      json={"texts": texts, "threshold": threshold})
        response.raise_for_status()
        data = response.json()

        items = []
        for i, item in enumerate(data.get("results", []) if isinstance(data, dict) else []):
            if isinstance(item, dict) and item.get("ok", True) and item.get("result") is not None:
                idx = int(item.get("index", i))
                items.append({"index": idx, "ok": True, "error": None,
                              "result": parse_result(item["result"],
                                                     fallback_text=texts[idx] if idx < len(texts) else "",
                                                     threshold=threshold)})
            else:
                items.append({"index": int(item.get("index", i)) if isinstance(item, dict) else i,
                              "ok": False, "result": None,
                              "error": (item or {}).get("error", "batch item failed") if isinstance(item, dict) else "invalid batch item"})
        return {"results": items}
