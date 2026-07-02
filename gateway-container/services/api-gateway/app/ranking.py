"""[참고자료 정렬] 검색(RAG)으로 받아온 후보 문서들을 "프롬프트에 넣을 순서"로 다듬는다.

하는 일 3가지:
    1. 점수 정규화 — 검색 점수를 0~1 범위로 맞춘다 (검색엔진마다 점수 크기가 달라서)
    2. 라벨 가산점 — 이번 발화의 인지왜곡 라벨과 관련된 기법 문서에 +0.3
    3. 중복 제거 후 상위 top_n 개만 반환
"""
from . import settings


def rerank(candidates: list[dict], primary: str, confidence: float,
           top_n: int | None = None) -> list[dict]:
    top_n = top_n or settings.RERANK_TOP_N
    if not candidates:
        return []

    # 1) 정규화 준비: 최고점과 최저점 사이의 폭(span)을 구한다
    scores = [float(c.get("score", 0.0)) for c in candidates]
    min_score, max_score = min(scores), max(scores)
    span = max_score - min_score

    # 2) 가산점 조건: 라벨이 정상/불충분이 아니고, 분류 확신이 50% 이상일 때만
    #    (확신이 낮은 라벨로 문서를 밀어주면 엉뚱한 자료가 앞에 올 수 있다)
    use_bias = primary not in ("정상", "불충분") and confidence >= 0.5
    deduped: dict[str, dict] = {}

    for candidate in candidates:
        raw = float(candidate.get("score", 0.0))
        normalized = 1.0 if span == 0 else (raw - min_score) / span
        # 문서의 metadata.distortions = 이 문서(상담 기법)가 다루는 왜곡 라벨 목록
        distortions = candidate.get("metadata", {}).get("distortions", [])
        final = normalized + (0.3 if use_bias and primary in distortions else 0.0)
        ranked = {**candidate, "score": final}
        cid = ranked.get("id")
        # 같은 id 문서가 여러 번 오면 점수가 높은 쪽만 남긴다
        if cid not in deduped or final > deduped[cid]["score"]:
            deduped[cid] = ranked

    # 3) 점수 내림차순 정렬 후 상위 top_n 개
    return sorted(deduped.values(), key=lambda c: c["score"], reverse=True)[:top_n]
