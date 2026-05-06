import json
import unittest
from pathlib import Path
from unittest.mock import patch

from _load_module import load

m = load()


class ExiftoolBatchTest(unittest.TestCase):
    def test_batch_returns_dict_keyed_by_path(self):
        fake_stdout = json.dumps([
            {"SourceFile": "/x/A.JPG",
             "DateTimeOriginal": "2026:05:03 12:00:00",
             "SerialNumber": "4012345"},
            {"SourceFile": "/x/B.MP4",
             "CreateDate": "2026:05:03 14:30:00"},
        ])
        with patch.object(m.subprocess, "run") as run:
            run.return_value.stdout = fake_stdout
            run.return_value.returncode = 0
            out = m.exiftool_batch(
                [Path("/x/A.JPG"), Path("/x/B.MP4")],
                tags=["DateTimeOriginal", "CreateDate", "SerialNumber"],
            )
        self.assertIn(Path("/x/A.JPG"), out)
        self.assertEqual(out[Path("/x/A.JPG")]["DateTimeOriginal"],
                         "2026:05:03 12:00:00")
        self.assertEqual(out[Path("/x/A.JPG")]["SerialNumber"], "4012345")
        self.assertEqual(out[Path("/x/B.MP4")]["CreateDate"],
                         "2026:05:03 14:30:00")

    def test_batch_handles_empty_input(self):
        out = m.exiftool_batch([], tags=["DateTimeOriginal"])
        self.assertEqual(out, {})

    def test_batch_returns_empty_on_nonzero_exit(self):
        with patch.object(m.subprocess, "run") as run:
            run.return_value.stdout = ""
            run.return_value.returncode = 1
            out = m.exiftool_batch([Path("/x/A.JPG")], tags=["DateTimeOriginal"])
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
