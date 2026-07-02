"""[외부 서비스 창구] Azure 등 외부 서비스 호출을 담당하는 어댑터 모음.

어댑터 = 외부 서비스의 복잡한 호출 방법을 감추고 간단한 함수 하나로 노출하는 중간층.
덕분에 respond_flow 는 "services.safety.check(text)" 처럼만 쓰면 되고,
Azure SDK 사용법이 바뀌어도 어댑터 파일 하나만 고치면 된다.
테스트(tests/)는 이 services 싱글톤의 어댑터를 가짜로 바꿔치기해서
네트워크 없이 전체 흐름을 검증한다.
"""
from .classifier import ClassifierAdapter
from .content_safety import SafetyAdapter
from .llm import LlmAdapter
from .retriever import RetrieverAdapter
from .speech import SpeechAdapter


class GatewayServiceAdapters:
    """다섯 개의 외부 서비스 창구를 한 객체에 모은 것."""

    def __init__(self):
        self.classifier = ClassifierAdapter()  # 인지왜곡 분류 (내부 cogdist 컨테이너)
        self.safety = SafetyAdapter()          # 위험 발화 탐지 (Azure Content Safety)
        self.retriever = RetrieverAdapter()    # 참고자료 검색 (Azure AI Search)
        self.llm = LlmAdapter()                # 답변 생성 (Azure OpenAI)
        self.speech = SpeechAdapter()          # 음성 변환 (Azure Speech STT/TTS)


# 서버 전체가 공유하는 인스턴스 (싱글톤)
services = GatewayServiceAdapters()
