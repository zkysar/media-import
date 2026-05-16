"""Output-layout tests: <dest>/<date>/<device-class>/<tx>/<category>/."""

import argparse
import inspect
import tempfile
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


class TestResolveSlugDest(unittest.TestCase):

    def test_mints_with_today_when_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = dji.resolve_slug_dest(root, "marple-pics", date(2026, 5, 16))
            self.assertEqual(out, root / "2026-05-16-marple-pics")

    def test_reuses_existing_dated_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "2026-05-13-marple-pics"
            existing.mkdir()
            out = dji.resolve_slug_dest(root, "marple-pics", date(2026, 5, 16))
            self.assertEqual(out, existing)

    def test_ignores_other_slugs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2026-05-13-other-shoot").mkdir()
            (root / "2026-05-13-marple-pics").mkdir()
            out = dji.resolve_slug_dest(root, "marple-pics", date(2026, 5, 16))
            self.assertEqual(out, root / "2026-05-13-marple-pics")

    def test_errors_on_multiple_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2026-05-13-marple-pics").mkdir()
            (root / "2026-04-01-marple-pics").mkdir()
            with self.assertRaises(SystemExit) as ctx:
                dji.resolve_slug_dest(root, "marple-pics", date(2026, 5, 16))
            self.assertIn("marple-pics", str(ctx.exception))

    def test_ignores_files_with_matching_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2026-05-13-marple-pics").touch()  # file, not dir
            out = dji.resolve_slug_dest(root, "marple-pics", date(2026, 5, 16))
            self.assertEqual(out, root / "2026-05-16-marple-pics")

    def test_handles_missing_root(self):
        # Root doesn't exist yet; should mint with today (parent created later).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "not-yet-created"
            out = dji.resolve_slug_dest(root, "marple-pics", date(2026, 5, 16))
            self.assertEqual(out, root / "2026-05-16-marple-pics")

    def test_ignores_undated_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "marple-pics").mkdir()  # no date prefix
            out = dji.resolve_slug_dest(root, "marple-pics", date(2026, 5, 16))
            self.assertEqual(out, root / "2026-05-16-marple-pics")


if __name__ == "__main__":
    unittest.main()
