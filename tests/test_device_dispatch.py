import tempfile
import unittest
from pathlib import Path

from _load_module import load

m = load()


class DeviceDispatchTest(unittest.TestCase):
    def test_dji_device_exposes_expected_hooks(self):
        d = m.DJI_MIC
        self.assertEqual(d.name, "dji-mic-2")
        self.assertEqual(d.device_class, "DJI-MICS")
        self.assertTrue(callable(d.detect))
        self.assertTrue(callable(d.discover))
        self.assertTrue(callable(d.build_plan))
        self.assertTrue(callable(d.completion_dates))

    def test_select_device_auto_returns_dji_for_dji_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            vol = Path(tmp)
            (vol / "TX01_MIC001_20260503_120000_orig.wav").write_bytes(b"")
            picked = m.select_device([vol], requested="auto")
            self.assertIs(picked, m.DJI_MIC)

    def test_select_device_explicit_dji(self):
        picked = m.select_device([], requested="dji")
        self.assertIs(picked, m.DJI_MIC)

    def test_select_device_auto_returns_sony_for_sony_card(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vol = Path(tmp)
            stills = vol / "DCIM" / "100MSDCF"
            stills.mkdir(parents=True)
            (stills / "DSC00001.JPG").write_bytes(b"")
            picked = m.select_device([vol], requested="auto")
            self.assertIs(picked, m.SONY_A7C)

    def test_select_device_auto_returns_sony_for_video_only_card(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vol = Path(tmp)
            (vol / "PRIVATE" / "M4ROOT" / "CLIP").mkdir(parents=True)
            picked = m.select_device([vol], requested="auto")
            self.assertIs(picked, m.SONY_A7C)

    def test_select_device_explicit_sony(self):
        picked = m.select_device([], requested="sony")
        self.assertIs(picked, m.SONY_A7C)

    def test_sony_detect_rejects_random_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vol = Path(tmp)
            (vol / "junk.txt").write_bytes(b"")
            self.assertFalse(m._sony_volume_detect(vol))


if __name__ == "__main__":
    unittest.main()
