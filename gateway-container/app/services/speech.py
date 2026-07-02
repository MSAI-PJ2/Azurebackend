"""[음성 창구] 음성→텍스트(STT), 텍스트→음성(TTS) — Azure Speech.

SDK 는 블로킹(동기)이라 어댑터가 모든 호출을 asyncio.to_thread 로 별도 스레드에
맡긴다 — 음성 변환 중에도 서버가 다른 요청을 처리할 수 있게.
필요 환경변수: AZURE_SPEECH_KEY, AZURE_SPEECH_REGION(기본 koreacentral),
AZURE_SPEECH_DEFAULT_VOICE(기본 ko-KR-SunHiNeural).
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import re
import tempfile

import azure.cognitiveservices.speech as speechsdk
import httpx

logger = logging.getLogger(__name__)

DEFAULT_VOICE = os.getenv("AZURE_SPEECH_DEFAULT_VOICE", "ko-KR-SunHiNeural")


def _speech_config(voice_name: str | None = None) -> speechsdk.SpeechConfig:
    """Azure Speech 접속 설정: 키/리전 + 인식 언어(한국어) + 합성 목소리/음질."""
    cfg = speechsdk.SpeechConfig(
        subscription=os.environ["AZURE_SPEECH_KEY"],
        region=os.environ.get("AZURE_SPEECH_REGION", "koreacentral"))
    cfg.speech_recognition_language = "ko-KR"
    cfg.speech_synthesis_voice_name = voice_name or DEFAULT_VOICE
    cfg.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm)
    return cfg


def _resolve_audio_bytes(audio: dict) -> bytes:
    """요청의 audio 필드에서 실제 오디오 바이트를 꺼낸다 (base64 디코딩 또는 URL 다운로드)."""
    kind = audio.get("kind")
    if kind == "base64":
        data = audio.get("data")
        if not data:
            raise ValueError("audio.data is required when audio.kind='base64'")
        # 브라우저가 "data:audio/webm;base64,...." 형태로 보내는 경우 앞부분을 떼어낸다
        if isinstance(data, str) and data.strip().startswith("data:") and "," in data:
            data = data.split(",", 1)[1]
        return base64.b64decode(data)
    if kind == "url":
        url = audio.get("url")
        if not url:
            raise ValueError("audio.url is required when audio.kind='url'")
        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
        return resp.content
    raise ValueError(f"unsupported audio.kind: {kind!r} (base64 | url)")


def _to_wav(raw: bytes, mime_type: str | None) -> bytes:
    """브라우저 녹음 포맷(webm/ogg 등)을 Azure 가 읽는 WAV(16kHz 모노)로 변환.

    변환에는 pydub + ffmpeg 가 필요하다 (Dockerfile 에서 ffmpeg 설치).
    변환에 실패하면 원본 그대로 시도해 본다 — 이미 WAV 였을 수도 있으므로.
    """
    if mime_type and "wav" in mime_type:
        return raw
    try:
        from pydub import AudioSegment
        fmt_map = {"webm": "webm", "ogg": "ogg", "mp4": "mp4", "m4a": "mp4"}
        fmt = next((v for k, v in fmt_map.items() if k in (mime_type or "")), "webm")
        seg = AudioSegment.from_file(io.BytesIO(raw), format=fmt)
        seg = seg.set_frame_rate(16_000).set_channels(1).set_sample_width(2)
        buf = io.BytesIO()
        seg.export(buf, format="wav")
        return buf.getvalue()
    except Exception as exc:
        logger.warning("오디오 포맷 변환 실패(%s), 원본 바이트로 시도", exc)
        return raw


def _recognize_once(audio: dict) -> speechsdk.SpeechRecognitionResult:
    """오디오 → WAV 변환 → 임시 파일로 저장 → Azure 1회 인식. STT 실행 로직은 여기 한 곳."""
    wav = _to_wav(_resolve_audio_bytes(audio), audio.get("mime_type"))
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav)
        tmp_path = f.name
    try:
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=_speech_config(),
            audio_config=speechsdk.audio.AudioConfig(filename=tmp_path))
        return recognizer.recognize_once_async().get()
    finally:
        try:
            os.unlink(tmp_path)  # 임시 파일은 결과와 무관하게 삭제
        except OSError:
            pass


def transcribe_audio_detailed(audio: dict) -> dict:
    """STT 결과를 SSE `stt` 이벤트 형식(dict)으로 반환. 예외도 error dict 로 감싼다 —
    STT 실패가 응답 스트림 전체를 죽이면 안 되기 때문."""
    base = {"provider": "azure", "language": audio.get("language") or "ko-KR",
            "mime_type": audio.get("mime_type"), "kind": audio.get("kind")}
    try:
        result = _recognize_once(audio)
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return {**base, "status": "completed", "transcript": result.text.strip(),
                    "confidence": None, "recognition_status": "RecognizedSpeech"}
        if result.reason == speechsdk.ResultReason.NoMatch:
            return {**base, "status": "no_match", "transcript": "", "confidence": None,
                    "recognition_status": "NoMatch", "reason": str(result.no_match_details)}
        cancel = speechsdk.CancellationDetails.from_result(result)
        return {**base, "status": "error", "transcript": "", "recognition_status": "Canceled",
                "reason": str(cancel.reason), "error": str(cancel.error_details)}
    except Exception as exc:
        return {**base, "status": "error", "transcript": "", "error": str(exc)}


def synthesize_speech_base64(text: str, voice_name: str | None = None) -> str:
    """텍스트 → 음성 합성 → base64 문자열(WAV). 실패 시 예외 (어댑터가 error dict 로 변환)."""
    synth = speechsdk.SpeechSynthesizer(speech_config=_speech_config(voice_name), audio_config=None)
    result = synth.speak_text_async(_strip_markdown(text)).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return base64.b64encode(result.audio_data).decode("ascii")
    cancel = speechsdk.CancellationDetails.from_result(result)
    raise RuntimeError(f"TTS canceled: {cancel.reason} / {cancel.error_details}")


def _strip_markdown(text: str) -> str:
    """음성으로 읽으면 어색한 표기(굵게 **, 제목 #, 링크, 이모지)를 제거한다."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub("[\U00010000-\U0010ffff\U0001F300-\U0001F9FF"
                  "\U00002700-\U000027BF\U0000FE00-\U0000FE0F]+", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class SpeechAdapter:
    async def transcribe_audio(self, audio: dict | None) -> dict:
        """음성 → 텍스트. 성공/실패 정보가 담긴 dict 를 돌려준다 (stt 이벤트 형식)."""
        return await asyncio.to_thread(transcribe_audio_detailed, audio)

    async def synthesize_tts(self, text: str, tts_options: dict | None) -> dict:
        """텍스트 → 음성(base64 WAV). 실패해도 예외 대신 error dict —
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
