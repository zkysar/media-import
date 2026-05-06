import unittest
from pathlib import Path
from unittest.mock import patch

from _load_module import load
m = load()

FIXTURE = Path(__file__).parent / "fixtures" / "sony-a7c-card"


class SonyScanTest(unittest.TestCase):
    def _common_meta(self):
        return {
            FIXTURE / "DCIM/100MSDCF/DSC00001.JPG": {
                "DateTimeOriginal": "2026:05:03 12:00:00",
                "SerialNumber": "4012345",
            },
            FIXTURE / "DCIM/100MSDCF/DSC00001.ARW": {
                "DateTimeOriginal": "2026:05:03 12:00:00",
                "SerialNumber": "4012345",
            },
            FIXTURE / "DCIM/100MSDCF/DSC00002.JPG": {
                "DateTimeOriginal": "2026:05:03 12:30:00",
                "SerialNumber": "4012345",
            },
            FIXTURE / "PRIVATE/M4ROOT/CLIP/C0001.MP4": {
                "CreateDate": "2026:05:03 14:00:00",
                "SerialNumber": "4012345",
            },
        }

    def test_scan_finds_three_groups(self):
        with patch.object(m, "exiftool_batch", return_value=self._common_meta()):
            groups = m.sony_discover([FIXTURE])
        kinds = sorted(g.kind for g in groups)
        self.assertEqual(kinds, ["photo", "photo", "video"])

    def test_scan_pairs_raw_and_jpeg(self):
        with patch.object(m, "exiftool_batch", return_value=self._common_meta()):
            groups = m.sony_discover([FIXTURE])
        photo_pairs = [g for g in groups
                        if g.kind == "photo"
                        and any(p.suffix == ".ARW" for p in g.files)]
        self.assertEqual(len(photo_pairs), 1)
        names = sorted(p.name for p in photo_pairs[0].files)
        self.assertEqual(names, ["DSC00001.ARW", "DSC00001.JPG"])

    def test_scan_skips_db_files(self):
        with patch.object(m, "exiftool_batch", return_value=self._common_meta()):
            groups = m.sony_discover([FIXTURE])
        flat = [str(p) for g in groups for p in g.files]
        self.assertFalse(any("MEDIAPRO" in p for p in flat))
        self.assertFalse(any("STATUS.BIN" in p for p in flat))
        self.assertFalse(any("AVF_INFO" in p for p in flat))
        self.assertFalse(any("PRIVATE/SONY" in p for p in flat))

    def test_scan_picks_up_video_sidecars(self):
        with patch.object(m, "exiftool_batch", return_value=self._common_meta()):
            groups = m.sony_discover([FIXTURE])
        videos = [g for g in groups if g.kind == "video"]
        self.assertEqual(len(videos), 1)
        names = sorted(p.name for p in videos[0].files)
        self.assertEqual(names, ["C0001.MP4", "C0001.THM", "C0001M01.XML"])

    def test_scan_drops_groups_without_exif_timestamp(self):
        with patch.object(m, "exiftool_batch", return_value={}):
            groups = m.sony_discover([FIXTURE])
        self.assertEqual(groups, [])


if __name__ == "__main__":
    unittest.main()
