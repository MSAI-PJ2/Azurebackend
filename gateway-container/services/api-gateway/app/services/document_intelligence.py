"""[문서 창구] 채팅 캡쳐 이미지 → 대화 로그 (OCR). 실제 처리는 document/kakao_ocr.py.

원본 파이프라인은 리포 루트 di/ (팀원 작업물, di/README.md 참고) — 게이트웨이는
그 복제본(services/document/)을 쓴다. DI SDK 는 블로킹이라 to_thread 로 오프로딩.
클라이언트는 첫 호출 때 생성(env 지연 검증 — 테스트는 이 어댑터를 가짜로 교체).
"""
import asyncio

from document.kakao_ocr import extract_conversation


class DocumentAdapter:
    async def extract_conversation(self, image: dict | None, sender_names: list[str] | None = None) -> dict:
        """이미지 → {status, conversation:[{speaker, content, time}], error?} (ocr 이벤트 형식)."""
        return await asyncio.to_thread(extract_conversation, image, sender_names)
