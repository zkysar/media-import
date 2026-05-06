import unittest
from pathlib import Path
from unittest.mock import patch

from _load_module import load
m = load()


class FfmpegExtractTest(unittest.TestCase):
    def test_extract_audio_invokes_ffmpeg_with_correct_args(self):
        with patch.object(m.subprocess, "run") as run:
            run.return_value.returncode = 0
            m.ffmpeg_extract_audio(Path("/tmp/c.mp4"), Path("/tmp/c.wav"))
            cmd = run.call_args[0][0]
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-vn", cmd)
        self.assertIn("/tmp/c.mp4", cmd)
        self.assertIn("/tmp/c.wav", cmd)
        self.assertIn("-ac", cmd)
        self.assertIn("1", cmd)
        self.assertIn("-ar", cmd)
        self.assertIn("16000", cmd)

    def test_extract_audio_raises_on_nonzero_exit(self):
        with patch.object(m.subprocess, "run") as run:
            run.return_value.returncode = 1
            run.return_value.stderr = "ffmpeg: input not found"
            with self.assertRaises(RuntimeError):
                m.ffmpeg_extract_audio(Path("/tmp/c.mp4"), Path("/tmp/c.wav"))


if __name__ == "__main__":
    unittest.main()
