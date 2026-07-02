"""[음성 창구] 음성→텍스트(STT), 텍스트→음성(TTS). 실제 처리는 common/speech_client.py.

Azure Speech SDK 는 동기(블로킹)라서 모든 호출을 asyncio.to_thread 로
별도 스레드에 맡긴다 — 음성 변환 중에도 서버가 다른 요청을 처리할 수 있게.
"""
import asyncio

from common.speech_client import synthesize_speech_base64, transcribe_audio_detailed


class SpeechAdapter:
    async def transcribe_audio(self, audio: dict | None) -> dict:
        """음성 → 텍스트. 성공/실패 정보가 담긴 dict 를 돌려준다 (stt 이벤트 형식)."""
        return await asyncio.to_thread(transcribe_audio_detailed, audio)

    async def synthesize_tts(self, text: str, tts_options: dict | None) -> dict:
        """텍스트 → 음성(base64 WAV). 실패해도 예외 대신 error dict 를 돌려준다 —
        음성 합성 실패 때문에 이미 보낸 텍스트 답변 스트림이 끊기면 안 되기 때문."""
        voice = (tts_options or {}).get("voice")
        try:
            audio_b64 = await asyncio.to_thread(synthesize_speech_base64, text, voice)
            return {"status": "completed", "provider": "azure", "text": text,
                    "mime_type": "audio/wav", "format": "wav",
                    "audio": {"kind": "base64", "data": audio_b64, "mime_type": "audio/wav"},
                    "audio_base64": audio_b64,  # 과거 프론트 호환용 별칭 (신규는 audio.data 사용)
                    "options": tts_options}
        except Exception as exc:
            return {"status": "error", "provider": "azure", "text": text,
                    "error": str(exc)[:300], "options": tts_options}
