"""Audio transcription service supporting Groq Whisper and OpenAI Whisper APIs."""

import json
import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger("herdr-bridge.speech")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class SpeechTranscriber:
    """Transcribes audio files (Telegram voice notes) into text."""

    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ):
        self.groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")

    @property
    def is_configured(self) -> bool:
        """Returns True if at least one speech-to-text backend is configured."""
        return bool(self.groq_api_key or self.openai_api_key)

    def transcribe(
        self, audio_bytes: bytes, filename: str = "voice.ogg"
    ) -> Tuple[bool, str]:
        """Transcribes raw audio bytes into text. Returns (success, text_or_error)."""
        if not self.is_configured:
            return (
                False,
                "Falta configurar una clave de transcripción. Agregá 'groq_api_key' "
                "en config.json para transcribir audios al instante.",
            )

        if not HAS_REQUESTS:
            return False, "El módulo 'requests' no está instalado para llamar a la API de audio."

        # Prefer Groq (ultra fast, ~300ms)
        if self.groq_api_key:
            return self._transcribe_groq(audio_bytes, filename)

        # Fallback to OpenAI Whisper
        return self._transcribe_openai(audio_bytes, filename)

    def _transcribe_groq(
        self, audio_bytes: bytes, filename: str
    ) -> Tuple[bool, str]:
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.groq_api_key}"}
        files = {"file": (filename, audio_bytes, "audio/ogg")}
        data = {
            "model": "whisper-large-v3-turbo",
            "temperature": "0.0",
        }
        try:
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=35)
            if resp.status_code == 200:
                result_text = resp.json().get("text", "").strip()
                if result_text:
                    return True, result_text
                return False, "La nota de voz no contenía texto audible."
            err_data = resp.json() if resp.text else {}
            err_msg = err_data.get("error", {}).get("message", resp.text)
            logger.error("Groq Whisper API HTTP %d: %s", resp.status_code, err_msg)
            return False, f"Error de transcripción Groq: {err_msg}"
        except Exception as e:
            logger.error("Error calling Groq Whisper API: %s", e)
            return False, f"Error de conexión con Groq: {e}"

    def _transcribe_openai(
        self, audio_bytes: bytes, filename: str
    ) -> Tuple[bool, str]:
        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.openai_api_key}"}
        files = {"file": (filename, audio_bytes, "audio/ogg")}
        data = {
            "model": "whisper-1",
            "temperature": "0.0",
        }
        try:
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=35)
            if resp.status_code == 200:
                result_text = resp.json().get("text", "").strip()
                if result_text:
                    return True, result_text
                return False, "La nota de voz no contenía texto audible."
            err_data = resp.json() if resp.text else {}
            err_msg = err_data.get("error", {}).get("message", resp.text)
            logger.error("OpenAI Whisper API HTTP %d: %s", resp.status_code, err_msg)
            return False, f"Error de transcripción OpenAI: {err_msg}"
        except Exception as e:
            logger.error("Error calling OpenAI Whisper API: %s", e)
            return False, f"Error de conexión con OpenAI: {e}"
