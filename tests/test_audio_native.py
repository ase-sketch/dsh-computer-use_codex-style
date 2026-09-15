from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from computer_use.audio_win import start_recording, stop_recording, write_silence_wav


class AudioNativeTests(unittest.TestCase):
    def test_silence_wav_is_riff(self) -> None:
        path = Path(tempfile.gettempdir()) / "cu-silence.wav"
        write_silence_wav(path, 80)
        data = path.read_bytes()
        self.assertTrue(data.startswith(b"RIFF"))
        self.assertGreater(len(data), 44)

    def test_start_stop_recording_writes_wav(self) -> None:
        path = Path(tempfile.gettempdir()) / "cu-record.wav"
        handle, backend = start_recording(path)
        self.assertIn(backend, {"ffmpeg", "wavein", "silence"})
        stopped = stop_recording(handle, path)
        data = stopped.read_bytes()
        self.assertTrue(data.startswith(b"RIFF"))
        self.assertGreater(stopped.stat().st_size, 44)

    def test_native_host_manifest(self) -> None:
        manifest = Path(__file__).resolve().parents[1] / "computer_use" / "native_host.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "com.computeruse.tabbridge")
        self.assertEqual(data["type"], "stdio")
        ext = Path(__file__).resolve().parents[1] / "computer_use" / "chrome_extension" / "manifest.json"
        perms = json.loads(ext.read_text(encoding="utf-8"))["permissions"]
        self.assertIn("nativeMessaging", perms)


if __name__ == "__main__":
    unittest.main()
