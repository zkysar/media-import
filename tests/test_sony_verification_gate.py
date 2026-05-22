import io
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from _load_module import load
m = load()


class SonySkipWhenUnverifiedTest(unittest.TestCase):
    """Unverified Sony is skipped (not fatal) in a multi-device run; other
    devices still import. A Sony-only unverified run finds nothing to do."""

    def setUp(self):
        self._orig = {
            "find": m.find_all_volumes,
            "validate": m.validate_runtime,
            "sony_detect": m.SONY_A7C.detect,
            "sony_disc": m.SONY_A7C.discover,
            "drone_detect": m.DJI_AIR_2.detect,
            "drone_disc": m.DJI_AIR_2.discover,
        }
        m.validate_runtime = lambda: None

    def tearDown(self):
        m.find_all_volumes = self._orig["find"]
        m.validate_runtime = self._orig["validate"]
        m.SONY_A7C.detect = self._orig["sony_detect"]
        m.SONY_A7C.discover = self._orig["sony_disc"]
        m.DJI_AIR_2.detect = self._orig["drone_detect"]
        m.DJI_AIR_2.discover = self._orig["drone_disc"]

    def test_unverified_sony_skipped_drone_proceeds(self):
        sony_vol = Path("/Volumes/SONY")
        drone_vol = Path("/Volumes/DRONE")
        drone_g = m.MediaGroup(
            kind="video",
            primary=drone_vol / "DCIM/100MEDIA/DJI_0001.MP4",
            files=[drone_vol / "DCIM/100MEDIA/DJI_0001.MP4"],
            timestamp=datetime(2026, 5, 3, 10, 0, 0),
            body_serial="UNKNOWN", size_bytes=2000, volume=drone_vol)
        m.find_all_volumes = lambda: [sony_vol, drone_vol]
        m.SONY_A7C.detect = lambda v: v == sony_vol
        m.SONY_A7C.discover = lambda vols: []  # should never be called once skipped
        m.DJI_AIR_2.detect = lambda v: v == drone_vol
        m.DJI_AIR_2.discover = lambda vols: [drone_g]

        with tempfile.TemporaryDirectory() as tmp:
            fake_marker = Path(tmp) / "sony-verified.json"  # absent → unverified
            out, err = io.StringIO(), io.StringIO()
            with patch.object(m, "SONY_VERIFICATION_PATH", fake_marker):
                with redirect_stdout(out), redirect_stderr(err):
                    rc = m.main(["--dest", tmp, "--device", "auto",
                                 "--days", "3650", "--yes", "--dry-run"])
            stdout, stderr = out.getvalue(), err.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("skipping Sony A7C", stderr)
        self.assertIn("Import Preview (dji-air-2)", stdout)
        self.assertNotIn("Import Preview (sony-a7c)", stdout)

    def test_sony_only_unverified_reports_no_media(self):
        sony_vol = Path("/Volumes/SONY")
        m.find_all_volumes = lambda: [sony_vol]
        m.SONY_A7C.detect = lambda v: v == sony_vol
        m.SONY_A7C.discover = lambda vols: []
        m.DJI_AIR_2.detect = lambda v: False

        with tempfile.TemporaryDirectory() as tmp:
            fake_marker = Path(tmp) / "sony-verified.json"
            out, err = io.StringIO(), io.StringIO()
            with patch.object(m, "SONY_VERIFICATION_PATH", fake_marker):
                with redirect_stdout(out), redirect_stderr(err):
                    rc = m.main(["--dest", tmp, "--device", "auto",
                                 "--days", "3650", "--yes", "--dry-run"])
            stderr = err.getvalue()
        self.assertEqual(rc, 2)
        self.assertIn("no importable media", stderr)


if __name__ == "__main__":
    unittest.main()
