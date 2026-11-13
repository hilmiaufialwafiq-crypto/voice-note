import io
import tempfile
import wave
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import app
from pydub.exceptions import CouldntDecodeError


def make_wav():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio_file:
        audio_file.setnchannels(1)
        audio_file.setsampwidth(2)
        audio_file.setframerate(16000)
        audio_file.writeframes(b"\x00\x00" * 1600)
    buffer.seek(0)
    return buffer


class VoiceWorkflowTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.database_patch = patch.object(app, "DATABASE", root / "test.db")
        self.upload_patch = patch.object(app, "UPLOAD_DIR", root / "uploads")
        self.database_patch.start()
        self.upload_patch.start()
        app.init_db()
        self.client = app.app.test_client()
        with self.client.session_transaction() as session:
            session["_csrf_token"] = "test-token"

    def tearDown(self):
        self.database_patch.stop()
        self.upload_patch.stop()
        self.temp_dir.cleanup()

    def post_data(self, **fields):
        return {"_csrf_token": "test-token", **fields}

    def test_record_upload_is_transcribed_and_saved_with_audio(self):
        with patch.object(app, "transcribe_audio", return_value="Halo, ini hasil transkripsi.") as transcribe:
            response = self.client.post(
                "/record",
                data=self.post_data(
                    title="Catatan suara",
                    category="Bahasa",
                    content="",
                    audio=(make_wav(), "rekaman.wav"),
                ),
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 302)
        transcribe.assert_called_once()
        note = app.get_note(1)
        self.assertEqual(note["content"], "Halo, ini hasil transkripsi.")
        self.assertTrue((app.UPLOAD_DIR / note["audio_file"]).is_file())
        detail = self.client.get(f"/notes/{note['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"Rekaman audio", detail.data)

    def test_wav_is_parsed_and_sent_to_indonesian_recognizer(self):
        audio_path = app.UPLOAD_DIR / "sample.wav"
        audio_path.write_bytes(make_wav().read())
        with patch.object(app.sr, "Recognizer") as recognizer_class:
            recognizer_class.return_value.recognize_google.return_value = "Selamat pagi"

            transcript = app.transcribe_audio(audio_path)

        self.assertEqual(transcript, "Selamat pagi")
        recognizer_class.return_value.recognize_google.assert_called_once()
        self.assertEqual(
            recognizer_class.return_value.recognize_google.call_args.kwargs["language"],
            "id-ID",
        )

    def test_unsupported_web_audio_decode_is_reported_as_value_error(self):
        audio_path = app.UPLOAD_DIR / "sample.webm"
        audio_path.write_bytes(b"not a decodable audio file")
        with patch("pydub.AudioSegment.from_file", side_effect=CouldntDecodeError("decode failed")):
            with self.assertRaisesRegex(ValueError, "Audio tidak dapat dibaca"):
                app.transcribe_audio(audio_path)

    def test_dashboard_and_recording_pages_load(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/record").status_code, 200)
        self.assertEqual(self.client.get("/upload").status_code, 200)


if __name__ == "__main__":
    import unittest

    unittest.main()
