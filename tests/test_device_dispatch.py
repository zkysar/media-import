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

    def test_select_device_explicit_dji_mic_2(self):
        picked = m.select_device([], requested="dji-mic-2")
        self.assertIs(picked, m.DJI_MIC)

    def test_parse_device_maps_dji_alias(self):
        # Deprecated alias is mapped at parse time (warns to stderr).
        canonical = m._parse_device("dji")
        self.assertEqual(canonical, "dji-mic-2")

    def test_parse_device_maps_sony_alias(self):
        canonical = m._parse_device("sony")
        self.assertEqual(canonical, "sony-a7c")

    def test_select_device_unknown_name_exits(self):
        with self.assertRaises(SystemExit):
            m.select_device([], requested="not-a-real-device")

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

    def test_select_device_explicit_sony_a7c(self):
        picked = m.select_device([], requested="sony-a7c")
        self.assertIs(picked, m.SONY_A7C)

    def test_select_device_explicit_dji_air_2(self):
        picked = m.select_device([], requested="dji-air-2")
        self.assertIs(picked, m.DJI_AIR_2)

    def test_dji_air_device_exposes_expected_hooks(self):
        d = m.DJI_AIR_2
        self.assertEqual(d.name, "dji-air-2")
        self.assertEqual(d.device_class, "DJI-DRONES")
        self.assertFalse(d.supports_transcribe)
        self.assertTrue(callable(d.detect))
        self.assertTrue(callable(d.discover))

    def test_sony_detect_rejects_random_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vol = Path(tmp)
            (vol / "junk.txt").write_bytes(b"")
            self.assertFalse(m._sony_volume_detect(vol))

    def test_select_devices_auto_returns_both_when_both_present(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            mic = Path(t1)
            (mic / "TX01_MIC001_20260503_120000_orig.wav").write_bytes(b"")
            sony = Path(t2)
            stills = sony / "DCIM" / "100MSDCF"
            stills.mkdir(parents=True)
            (stills / "DSC00001.JPG").write_bytes(b"")
            picked = m.select_devices([mic, sony], requested="auto")
            # ALL_DEVICES order: DJI_MIC, SONY_A7C, DJI_AIR_2
            self.assertEqual(picked, [m.DJI_MIC, m.SONY_A7C])

    def test_select_devices_explicit_returns_single(self):
        self.assertEqual(m.select_devices([], requested="sony-a7c"), [m.SONY_A7C])

    def test_select_devices_auto_none_present_exits(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vol = Path(tmp)
            (vol / "junk.txt").write_bytes(b"")
            with self.assertRaises(SystemExit):
                m.select_devices([vol], requested="auto")

    def test_select_devices_unknown_name_exits(self):
        with self.assertRaises(SystemExit):
            m.select_devices([], requested="not-a-real-device")


if __name__ == "__main__":
    unittest.main()
