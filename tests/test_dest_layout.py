"""Output-layout tests: <dest>/<date>/<device-class>/<tx>/<category>/."""

import argparse
import inspect
import unittest
from datetime import date
from pathlib import Path

from _load_module import load

dji = load()


class TestDestDirFor(unittest.TestCase):

    def test_edit_audio_path(self):
        p = dji.dest_dir_for(Path("/out"), date(2026, 5, 3), "TX01", "edit")
        self.assertEqual(p, Path("/out/RAW/2026-05-03/DJI-MICS/TX01/EDIT"))

    def test_orig_audio_path(self):
        p = dji.dest_dir_for(Path("/out"), date(2026, 5, 3), "TX02", "orig")
        self.assertEqual(p, Path("/out/RAW/2026-05-03/DJI-MICS/TX02/ORIG"))

    def test_transcripts_path_is_peer_of_edit_orig(self):
        p = dji.dest_dir_for(Path("/out"), date(2026, 5, 3), "TX01",
                             dji.TRANSCRIPTS_CATEGORY)
        self.assertEqual(p, Path("/out/RAW/2026-05-03/DJI-MICS/TX01/TRANSCRIPTS"))

    def test_category_is_uppercased(self):
        # Callers pass lowercase chain.version; folder is uppercased.
        lower = dji.dest_dir_for(Path("/out"), date(2026, 5, 3), "TX01", "edit")
        upper = dji.dest_dir_for(Path("/out"), date(2026, 5, 3), "TX01", "EDIT")
        self.assertEqual(lower, upper)

    def test_date_level_always_present_for_single_date(self):
        p = dji.dest_dir_for(Path("/out"), date(2026, 5, 3), "TX01", "edit")
        self.assertIn("2026-05-03", p.parts)

    def test_raw_is_top_level_under_dest(self):
        p = dji.dest_dir_for(Path("/out"), date(2026, 5, 3), "TX01", "edit")
        self.assertEqual(p.parts[1], "out")
        self.assertEqual(p.parts[2], "RAW")

    def test_device_class_constant(self):
        self.assertEqual(dji.DJI_DEVICE_CLASS, "DJI-MICS")

    def test_different_dates_yield_different_dirs(self):
        a = dji.dest_dir_for(Path("/out"), date(2026, 5, 3), "TX01", "edit")
        b = dji.dest_dir_for(Path("/out"), date(2026, 5, 4), "TX01", "edit")
        self.assertNotEqual(a, b)


class TestTranscribeIdempotencyPath(unittest.TestCase):
    """Guards against the runner regressing to `audio.with_suffix('.txt')`.

    Transcripts live in a sibling TRANSCRIPTS dir, not next to the audio.
    Both the planner (build_plan) and the runner (do_transcribe) must
    derive the .txt path from output_dir, otherwise re-runs disagree.
    """

    def test_runner_idempotency_uses_output_dir_not_audio_dir(self):
        # The runner's idempotency check happens inside run_transcribes.
        # Inspect its source to confirm it derives the transcript path from
        # op.output_dir rather than op.audio's own folder. Full integration
        # would need ffmpeg+whisper, so this is a structural test.
        src = inspect.getsource(dji.run_transcribes)
        self.assertIn("op.output_dir", src,
                      "run_transcribes must derive the transcript path from "
                      "op.output_dir (transcripts dir), not op.audio's "
                      "folder. See review fix for runner-vs-planner drift.")
        # Guard against either extension landing back on op.audio's folder
        # (e.g. via with_suffix), which would silently fall back to the
        # old co-located layout.
        for bad in ('op.audio.with_suffix(".txt")',
                    'op.audio.with_suffix(".srt")'):
            self.assertNotIn(bad, src,
                             f"Runner is using {bad!r}; transcripts must be "
                             "looked up under op.output_dir.")


class TestParseSlug(unittest.TestCase):

    def test_accepts_lowercase_with_dashes(self):
        for ok in ("marple-pics", "summer-content", "tx01", "a", "a-b-c-d"):
            self.assertEqual(dji._parse_slug(ok), ok)

    def test_rejects_uppercase(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            dji._parse_slug("Marple-Pics")

    def test_rejects_spaces(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            dji._parse_slug("marple pics")

    def test_rejects_underscore(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            dji._parse_slug("marple_pics")

    def test_rejects_leading_or_trailing_dash(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            dji._parse_slug("-marple")
        with self.assertRaises(argparse.ArgumentTypeError):
            dji._parse_slug("marple-")

    def test_rejects_double_dash(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            dji._parse_slug("marple--pics")

    def test_rejects_empty(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            dji._parse_slug("")


class TestEarliestShootDate(unittest.TestCase):
    """Date proposed for <dest>/<date>-<slug>/ comes from media, not today."""

    def _chain(self, d: date):
        # Minimal stand-in for build_chains output: only date_bucket is read.
        class _C: pass
        c = _C()
        c.date_bucket = d
        return c

    def _item(self, d: date):
        # Minimal stand-in for MediaGroup: only .timestamp is read.
        from datetime import datetime
        class _G: pass
        g = _G()
        g.timestamp = datetime(d.year, d.month, d.day, 12, 0, 0)
        return g

    def test_returns_none_when_no_dates(self):
        self.assertIsNone(dji._earliest_shoot_date([], []))

    def test_picks_min_across_mic_chains(self):
        chains = [self._chain(date(2026, 5, 8)),
                  self._chain(date(2026, 5, 7)),
                  self._chain(date(2026, 5, 9))]
        self.assertEqual(dji._earliest_shoot_date([], chains), date(2026, 5, 7))

    def test_picks_min_across_sony_drone_items(self):
        items = [self._item(date(2026, 5, 8)),
                 self._item(date(2026, 5, 7)),
                 self._item(date(2026, 5, 9))]
        self.assertEqual(dji._earliest_shoot_date(items, []),
                         date(2026, 5, 7))

    def test_single_date_imports(self):
        chains = [self._chain(date(2026, 5, 16))]
        self.assertEqual(dji._earliest_shoot_date([], chains),
                         date(2026, 5, 16))


if __name__ == "__main__":
    unittest.main()
