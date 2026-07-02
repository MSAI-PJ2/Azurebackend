"""Azure Speech STT/TTS 어댑터. SDK 는 블로킹이므로 전부 to_thread 로 오프로딩."""
import asyncio

from common.speech_client import synthesize_speech_base64, transcribe_audio_detailed


class SpeechAdapter:
    async def transcribe_audio(self, audio: dict | None) -> dict:
        return await asyncio.to_thread(transcribe_audio_detailed, audio)

    async def synthesize_tts(self, text: str, tts_options: dict | None) -> dict:
        """TTS payload 생성. 실패해도 스트림이 끊기지 않게 error payload 로 반환."""
        voice = (tts_options or {}).get("voice")
        try:
            audio_b64 = await asyncio.to_thread(synthesize_speech_base64, text, voice)
            return {"status": "completed", "provider": "azure", "text": text,
                    "mime_type": "audio/wav", "format": "wav",
                    "audio": {"kind": "base64", "data": audio_b64, "mime_type": "audio/wav"},
                    "audio_base64": audio_b64,  # 과거 프론트 호환 별칭
                    "options": tts_options}
        except Exception as exc:
            return {"status": "error", "provider": "azure", "text": text,
                    "error": str(exc)[:300], "options": tts_options}
