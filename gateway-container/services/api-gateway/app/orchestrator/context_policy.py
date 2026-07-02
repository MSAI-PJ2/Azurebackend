"""Context Policy Layer — 라벨별 응답 방식은 POLICIES 만 수정한다.

라우팅: ① safety unsafe → CRISIS_POLICY(최우선) ② primary ∈ POLICIES → 해당 정책
       ③ 그 외 왜곡 라벨 → DEFAULT_POLICY. prompt_strategy 는 prompts.PROMPT_STRATEGIES 키.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ContextPolicy:
    name: str                     # 세션 턴 policy 메타데이터로 저장됨
    prompt_strategy: str
    use_rag: bool = True
    rag_top_n: int | None = None  # None = settings.RERANK_TOP_N
    is_crisis: bool = False       # True 면 LLM 우회, 고정 위기 메시지 (crisis.py)

    def as_metadata(self) -> dict:
        return {"name": self.name, "prompt_strategy": self.prompt_strategy, "use_rag": self.use_rag}


CRISIS_POLICY = ContextPolicy("crisis_override", "cbt_label_guided", use_rag=False, is_crisis=True)
DEFAULT_POLICY = ContextPolicy("cbt_label_guided", "cbt_label_guided")

POLICIES: dict[str, ContextPolicy] = {
    "정상": ContextPolicy("normal_supportive", "supportive", rag_top_n=2),
    "불충분": ContextPolicy("insufficient_clarify", "clarify", use_rag=False),
    # 예) "흑백 사고": ContextPolicy("dichotomous_deep", "cbt_label_guided", rag_top_n=6),
}

# [도입 예정] '불충분' 최근 N턴 재분류: 최근 user 발화들을 이어붙여 재분류하고
# 왜곡 라벨이 나오면 그 정책을 적용. 구현 위치는 respond_flow 의 resolve() 직후.
# 분류기 호출 1회 추가되므로 지연시간 확인 후 도입.


def resolve(safety: dict, classification: dict) -> ContextPolicy:
    if not safety.get("safe", True):
        return CRISIS_POLICY
    return POLICIES.get(classification.get("primary", ""), DEFAULT_POLICY)
