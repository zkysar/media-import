import argparse
import unittest
from datetime import datetime, date
from pathlib import Path

from _load_module import load
m = load()


class SonyLayoutTest(unittest.TestCase):
    def test_photo_dest_dir_shape(self):
        d = m.sony_dest_dir_for(Path("/dest"), date(2026, 5, 3),
                                 "4012345", "photo")
        self.assertEqual(
            d, Path("/dest/RAW/2026-05-03/SONY-A7C/4012345/PHOTOS"))

    def test_video_dest_dir_shape(self):
        d = m.sony_dest_dir_for(Path("/dest"), date(2026, 5, 3),
                                 "4012345", "video")
        self.assertEqual(
            d, Path("/dest/RAW/2026-05-03/SONY-A7C/4012345/VIDEOS"))


if __name__ == "__main__":
    unittest.main()
