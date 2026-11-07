"""Unit tests for SpeechTranscriber."""

import unittest
from unittest.mock import MagicMock, patch

from bridge.adapters.speech.transcriber import SpeechTranscriber


class TestSpeechTranscriber(unittest.TestCase):
    def test_not_configured_when_no_keys(self):
        transcriber = SpeechTranscriber(groq_api_key=None, openai_api_key=None)
        self.assertFalse(transcriber.is_configured)
        ok, msg = transcriber.transcribe(b"dummy")
        self.assertFalse(ok)
        self.assertIn("Falta configurar", msg)

    def test_configured_when_groq_key_present(self):
        transcriber = SpeechTranscriber(groq_api_key="gsk_123")
        self.assertTrue(transcriber.is_configured)

    @patch("bridge.adapters.speech.transcriber.requests.post")
    def test_groq_transcription_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "ejecutar pruebas unitarias"}
        mock_post.return_value = mock_resp

        transcriber = SpeechTranscriber(groq_api_key="gsk_123")
        ok, text = transcriber.transcribe(b"fake-bytes", filename="voice.ogg")
        self.assertTrue(ok)
        self.assertEqual(text, "ejecutar pruebas unitarias")


if __name__ == "__main__":
    unittest.main()
