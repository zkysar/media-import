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

    def test_video_transcribe_extracts_audio_into_transcripts_dir(self):
        args = argparse.Namespace(
            dest=Path("/dest"), from_date=None, to_date=None, days=None,
            transcribe=True, model="small")
        g = m.SonyGroup(
            kind="video",
            primary=Path("/vol/PRIVATE/M4ROOT/CLIP/C0001.MP4"),
            files=[Path("/vol/PRIVATE/M4ROOT/CLIP/C0001.MP4")],
            timestamp=datetime(2026, 5, 3, 14, 0, 0),
            body_serial="4012345",
            size_bytes=100,
            volume=Path("/vol"))
        plan = m.sony_build_plan([g], args)
        self.assertEqual(len(plan.transcribes), 1)
        self.assertEqual(len(plan.audio_extracts), 1)
        ax = plan.audio_extracts[0]
        self.assertEqual(
            ax.src,
            Path("/dest/RAW/2026-05-03/SONY-A7C/4012345/VIDEOS/C0001.MP4"))
        self.assertEqual(
            ax.dst,
            Path("/dest/RAW/2026-05-03/SONY-A7C/4012345/TRANSCRIPTS/C0001.wav"))
        op = plan.transcribes[0]
        self.assertEqual(
            op.output_dir,
            Path("/dest/RAW/2026-05-03/SONY-A7C/4012345/TRANSCRIPTS"))
        self.assertEqual(op.audio, ax.dst)

    def test_video_no_transcribe_when_flag_off(self):
        args = argparse.Namespace(
            dest=Path("/dest"), from_date=None, to_date=None, days=None,
            transcribe=False, model=None)
        g = m.SonyGroup(
            kind="video",
            primary=Path("/vol/PRIVATE/M4ROOT/CLIP/C0001.MP4"),
            files=[Path("/vol/PRIVATE/M4ROOT/CLIP/C0001.MP4")],
            timestamp=datetime(2026, 5, 3, 14, 0, 0),
            body_serial="4012345",
            size_bytes=100,
            volume=Path("/vol"))
        plan = m.sony_build_plan([g], args)
        self.assertEqual(plan.transcribes, [])
        self.assertEqual(plan.audio_extracts, [])


if __name__ == "__main__":
    unittest.main()
