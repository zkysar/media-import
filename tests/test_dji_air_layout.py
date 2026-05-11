import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _load_module import load
m = load()

FIXTURE = Path(__file__).parent / "fixtures" / "dji-air-2-card"


def _args(dest):
    return argparse.Namespace(
        dest=dest, from_date=None, to_date=None, days=None,
    )


def _meta():
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


class DjiAirLayoutTest(unittest.TestCase):
    def test_photos_route_to_raw_photos(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            with patch.object(m, "exiftool_batch", return_value=_meta()):
                groups = m.dji_air_discover([FIXTURE])
            plan = m.dji_air_build_plan(groups, _args(dest))

            jpg_dsts = [op.dst for op in plan.singleton_moves
                        if op.dst.name.endswith(".JPG")]
            for d in jpg_dsts:
                rel = d.relative_to(dest)
                self.assertEqual(rel.parts[0], "RAW")
                self.assertEqual(rel.parts[1], "2026-05-07")
                self.assertEqual(rel.parts[2], "DJI-DRONES")
                self.assertEqual(rel.parts[3], "PHOTOS")

    def test_videos_and_sidecars_route_to_raw_videos(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            with patch.object(m, "exiftool_batch", return_value=_meta()):
                groups = m.dji_air_discover([FIXTURE])
            plan = m.dji_air_build_plan(groups, _args(dest))

            video_files = [op.dst for op in plan.singleton_moves
                           if op.dst.name.startswith("DJI_001") and not op.dst.name.endswith(".JPG")]
            self.assertEqual(len(video_files), 6)   # 2 MP4 + 2 THM + 2 SCR
            for d in video_files:
                rel = d.relative_to(dest)
                self.assertEqual(rel.parts[0], "RAW")
                self.assertEqual(rel.parts[2], "DJI-DRONES")
                self.assertEqual(rel.parts[3], "VIDEOS")

    def test_flightlog_routes_to_flightlogs_sibling(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            with patch.object(m, "exiftool_batch", return_value=_meta()):
                groups = m.dji_air_discover([FIXTURE])
            plan = m.dji_air_build_plan(groups, _args(dest))

            flight_op = next(op for op in plan.singleton_moves
                             if op.dst.name == "dji.gis")
            rel = flight_op.dst.relative_to(dest)
            # FLIGHTLOGS/<date>/dji.gis — sibling to RAW/, NOT under RAW/.
            self.assertEqual(rel.parts[0], "FLIGHTLOGS")
            self.assertNotIn("RAW", rel.parts)
            self.assertNotIn("DJI-DRONES", rel.parts)

    def test_supports_transcribe_is_false(self):
        self.assertFalse(m.DJI_AIR_2.supports_transcribe)


if __name__ == "__main__":
    unittest.main()
