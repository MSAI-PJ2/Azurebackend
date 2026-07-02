"""외부 서비스 어댑터 경계 — 컴포넌트당 파일 하나. 테스트는 services 싱글톤의 어댑터를 교체한다."""
from .classifier import ClassifierAdapter
from .content_safety import SafetyAdapter
from .llm import LlmAdapter
from .retriever import RetrieverAdapter
from .speech import SpeechAdapter


class GatewayServiceAdapters:
    def __init__(self):
        self.classifier = ClassifierAdapter()
        self.safety = SafetyAdapter()
        self.retriever = RetrieverAdapter()
        self.llm = LlmAdapter()
        self.speech = SpeechAdapter()


services = GatewayServiceAdapters()
