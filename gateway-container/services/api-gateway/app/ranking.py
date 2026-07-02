"""RAG 후보 재정렬: 0~1 정규화 + 분류 라벨 일치 문서 가산점(+0.3) + 중복 제거 + top_n."""
from . import settings


def rerank(candidates: list[dict], primary: str, confidence: float,
           top_n: int | None = None) -> list[dict]:
    top_n = top_n or settings.RERANK_TOP_N
    if not candidates:
        return []

    scores = [float(c.get("score", 0.0)) for c in candidates]
    min_score, max_score = min(scores), max(scores)
    span = max_score - min_score

    # 정상/불충분이거나 분류 확신이 낮으면 라벨 가산점 없음
    use_bias = primary not in ("정상", "불충분") and confidence >= 0.5
    deduped: dict[str, dict] = {}

    for candidate in candidates:
        raw = float(candidate.get("score", 0.0))
        normalized = 1.0 if span == 0 else (raw - min_score) / span
        distortions = candidate.get("metadata", {}).get("distortions", [])
        final = normalized + (0.3 if use_bias and primary in distortions else 0.0)
        ranked = {**candidate, "score": final}
        cid = ranked.get("id")
        if cid not in deduped or final > deduped[cid]["score"]:
            deduped[cid] = ranked

    return sorted(deduped.values(), key=lambda c: c["score"], reverse=True)[:top_n]
