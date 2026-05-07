import unittest
from pathlib import Path
from unittest.mock import patch

from _load_module import load
m = load()

FIXTURE = Path(__file__).parent / "fixtures" / "dji-air-2-card"


class DjiAirScanTest(unittest.TestCase):
    def _meta(self):
        # Two photos with full EXIF (incl. SerialNumber); two videos with
        # only QuickTime CreateDate (mirrors real Mavic Air 2 metadata).
        return {
            FIXTURE / "DCIM/100MEDIA/DJI_0001.JPG": {
                "DateTimeOriginal": "2026:05:07 13:00:00",
                "SerialNumber": "EXAMPLE0000001",
            },
            FIXTURE / "DCIM/100MEDIA/DJI_0002.JPG": {
                "DateTimeOriginal": "2026:05:07 13:05:00",
                "SerialNumber": "EXAMPLE0000001",
            },
            FIXTURE / "DCIM/100MEDIA/DJI_0014.MP4": {
                "CreateDate": "2026:05:07 20:06:14",
            },
            FIXTURE / "DCIM/100MEDIA/DJI_0015.MP4": {
                "CreateDate": "2026:05:07 20:10:17",
            },
        }

    def test_volume_detect(self):
        self.assertTrue(m._dji_air_volume_detect(FIXTURE))

    def test_volume_detect_rejects_random_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(m._dji_air_volume_detect(Path(tmp)))

    def test_discover_finds_seven_groups(self):
        with patch.object(m, "exiftool_batch", return_value=self._meta()):
            groups = m.dji_air_discover([FIXTURE])
        kinds = sorted(g.kind for g in groups)
        self.assertEqual(kinds, ["flightlog", "photo", "photo", "video", "video"])

    def test_videos_pair_with_thm_and_scr_sidecars(self):
        with patch.object(m, "exiftool_batch", return_value=self._meta()):
            groups = m.dji_air_discover([FIXTURE])
        videos = [g for g in groups if g.kind == "video"]
        self.assertEqual(len(videos), 2)
        for v in videos:
            names = sorted(p.name for p in v.files)
            self.assertEqual(len(names), 3)
            stem = v.primary.stem
            self.assertEqual(names, [f"{stem}.MP4", f"{stem}.SCR", f"{stem}.THM"])

    def test_videos_inherit_serial_from_jpg_on_same_volume(self):
        # MP4 metadata lacks SerialNumber; per-volume fallback uses any JPG's.
        with patch.object(m, "exiftool_batch", return_value=self._meta()):
            groups = m.dji_air_discover([FIXTURE])
        videos = [g for g in groups if g.kind == "video"]
        for v in videos:
            self.assertEqual(v.body_serial, "EXAMPLE0000001")

    def test_videos_serial_unknown_when_no_jpg_on_volume(self):
        # Only MP4 metadata; no JPG ever scanned.
        meta = {k: v for k, v in self._meta().items() if k.suffix == ".MP4"}
        # Also remove the JPGs so they don't get a primary record.
        # Discover still runs them through, but with no CreateDate they'd be
        # dropped — except we have DateTimeOriginal=None for JPGs, so they
        # disappear naturally.
        meta_no_jpg = {k: v for k, v in meta.items()}
        with patch.object(m, "exiftool_batch", return_value=meta_no_jpg):
            groups = m.dji_air_discover([FIXTURE])
        videos = [g for g in groups if g.kind == "video"]
        for v in videos:
            self.assertEqual(v.body_serial, "UNKNOWN")

    def test_flightlog_group_has_correct_path(self):
        with patch.object(m, "exiftool_batch", return_value=self._meta()):
            groups = m.dji_air_discover([FIXTURE])
        flight = [g for g in groups if g.kind == "flightlog"]
        self.assertEqual(len(flight), 1)
        self.assertEqual(flight[0].primary.name, "dji.gis")
        self.assertEqual(flight[0].files, [flight[0].primary])

    def test_dropped_groups_without_timestamp(self):
        # Empty meta → no group survives.
        with patch.object(m, "exiftool_batch", return_value={}):
            groups = m.dji_air_discover([FIXTURE])
        # Flight log uses mtime, not exif — it survives even without exif.
        non_flight = [g for g in groups if g.kind != "flightlog"]
        self.assertEqual(non_flight, [])


if __name__ == "__main__":
    unittest.main()
