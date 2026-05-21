import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, date
from pathlib import Path

from _load_module import load
m = load()


class SonyVerifiedPredicateTest(unittest.TestCase):
    def test_returns_false_when_marker_absent(self):
        orig = m.SONY_VERIFICATION_PATH
        try:
            m.SONY_VERIFICATION_PATH = Path("/nonexistent/sony-verified.json")
            self.assertFalse(m._sony_is_verified())
        finally:
            m.SONY_VERIFICATION_PATH = orig

    def test_returns_true_when_marker_present(self):
        orig = m.SONY_VERIFICATION_PATH
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                marker = Path(f.name)
            m.SONY_VERIFICATION_PATH = marker
            self.assertTrue(m._sony_is_verified())
        finally:
            m.SONY_VERIFICATION_PATH = orig
            marker.unlink(missing_ok=True)


class ResolveDateRangeTest(unittest.TestCase):
    def _args(self, **kw):
        base = dict(days=None, from_date=None, to_date=None)
        base.update(kw)
        return argparse.Namespace(**base)

    def test_days_sets_window_ignoring_default_dates(self):
        args = self._args(days=2)
        m.resolve_date_range(args, [date(2000, 1, 1)])
        self.assertEqual(args.to_date, date.today())
        self.assertEqual((args.to_date - args.from_date).days, 2)

    def test_no_flags_infers_from_earliest_default_date(self):
        args = self._args()
        m.resolve_date_range(args, [date(2026, 5, 3), date(2026, 5, 1), date(2026, 5, 7)])
        self.assertEqual(args.from_date, date(2026, 5, 1))
        self.assertEqual(args.to_date, date.today())

    def test_no_flags_no_dates_raises(self):
        args = self._args()
        with self.assertRaises(SystemExit):
            m.resolve_date_range(args, [])


class PreparedImportTest(unittest.TestCase):
    def test_fields_and_defaults(self):
        p = m.PreparedImport(
            device=m.DJI_MIC, volumes=[Path("/v")], items=[], chains=[],
            plan=m.Plan(), est={})
        self.assertIs(p.device, m.DJI_MIC)
        self.assertEqual(p.volumes, [Path("/v")])
        self.assertEqual(p.items, [])
        self.assertEqual(p.chains, [])
        self.assertIsInstance(p.plan, m.Plan)
        self.assertEqual(p.est, {})


class CombinedPreviewTest(unittest.TestCase):
    def _sony_prepared(self, dest):
        args = argparse.Namespace(
            dest=dest, from_date=None, to_date=None, days=None,
            transcribe=False, model=None, slug=None)
        g = m.MediaGroup(
            kind="photo",
            primary=Path("/svol/DCIM/100MSDCF/DSC00001.JPG"),
            files=[Path("/svol/DCIM/100MSDCF/DSC00001.JPG")],
            timestamp=datetime(2026, 5, 3, 9, 0, 0),
            body_serial="UNKNOWN", size_bytes=1000, volume=Path("/svol"))
        plan = m.sony_build_plan([g], args)
        est = m.estimate_seconds(plan, m.DEFAULT_RATES, None, False)
        return m.PreparedImport(m.SONY_A7C, [Path("/svol")], [g], [], plan, est)

    def _drone_prepared(self, dest):
        args = argparse.Namespace(
            dest=dest, from_date=None, to_date=None, days=None,
            transcribe=False, model=None, slug=None)
        g = m.MediaGroup(
            kind="video",
            primary=Path("/dvol/DCIM/100MEDIA/DJI_0001.MP4"),
            files=[Path("/dvol/DCIM/100MEDIA/DJI_0001.MP4")],
            timestamp=datetime(2026, 5, 3, 10, 0, 0),
            body_serial="UNKNOWN", size_bytes=2000, volume=Path("/dvol"))
        plan = m.dji_air_build_plan([g], args)
        est = m.estimate_seconds(plan, m.DEFAULT_RATES, None, False)
        return m.PreparedImport(m.DJI_AIR_2, [Path("/dvol")], [g], [], plan, est)

    def test_combined_preview_lists_both_devices_and_one_footer(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            args = argparse.Namespace(
                dest=dest, from_date=None, to_date=None, days=None,
                transcribe=False, model=None, slug=None, version="both", mic="all")
            prepped = [self._sony_prepared(dest), self._drone_prepared(dest)]
            out = m.format_combined_preview(prepped, args)
            self.assertIn("Import Preview (sony-a7c)", out)
            self.assertIn("Import Preview (dji-air-2)", out)
            # exactly one shared footer:
            self.assertEqual(out.count("Disk space at dest:"), 1)
            self.assertEqual(out.count("Estimated time:"), 1)


class MainMultiDeviceTest(unittest.TestCase):
    def setUp(self):
        self._orig_find = m.find_all_volumes
        self._orig_mic_detect = m.DJI_MIC.detect
        self._orig_mic_disc = m.DJI_MIC.discover
        self._orig_drone_detect = m.DJI_AIR_2.detect
        self._orig_drone_disc = m.DJI_AIR_2.discover
        self._orig_validate = m.validate_runtime

    def tearDown(self):
        m.find_all_volumes = self._orig_find
        m.DJI_MIC.detect = self._orig_mic_detect
        m.DJI_MIC.discover = self._orig_mic_disc
        m.DJI_AIR_2.detect = self._orig_drone_detect
        m.DJI_AIR_2.discover = self._orig_drone_disc
        m.validate_runtime = self._orig_validate

    def test_dry_run_previews_both_devices(self):
        with tempfile.TemporaryDirectory() as srcdir:
            mic_vol = Path(srcdir) / "MIC"
            drone_vol = Path(srcdir) / "DRONE"
            drone_media = drone_vol / "DCIM" / "100MEDIA"
            drone_media.mkdir(parents=True)
            drone_src = drone_media / "DJI_0001.MP4"
            drone_src.write_bytes(b"\x00" * 2000)

            # Clip fields (verified): path, tx, clip_idx, start, version, wav, volume.
            # size_bytes is a derived property (path.stat()), not a constructor arg;
            # the path won't exist in the test, so size reads as 0 — fine for dry-run.
            # Wav positional order: fmt_code, channels, sample_rate, block_align,
            # bits_per_sample, data_offset, data_size (here: 60s of 48k/16-bit stereo).
            clip = m.Clip(
                path=mic_vol / "TX01_MIC001_20260503_120000_orig.wav",
                tx="TX01", clip_idx=1,
                start=datetime(2026, 5, 3, 12, 0, 0),
                version="orig",
                wav=m.Wav(1, 2, 48000, 4, 16, 44, 48000 * 4 * 60),
                volume=mic_vol)
            drone_g = m.MediaGroup(
                kind="video",
                primary=drone_src,
                files=[drone_src],
                timestamp=datetime(2026, 5, 3, 10, 0, 0),
                body_serial="UNKNOWN", size_bytes=2000, volume=drone_vol)

            m.validate_runtime = lambda: None
            m.find_all_volumes = lambda: [mic_vol, drone_vol]
            m.DJI_MIC.detect = lambda v: v == mic_vol
            m.DJI_MIC.discover = lambda vols: [clip]
            m.DJI_AIR_2.detect = lambda v: v == drone_vol
            m.DJI_AIR_2.discover = lambda vols: [drone_g]

            with tempfile.TemporaryDirectory() as tmp:
                buf = io.StringIO()
                with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                    rc = m.main(["--dest", tmp, "--device", "auto",
                                 "--days", "3650", "--yes", "--dry-run"])
                out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Import Preview (dji-mic-2)", out)
        self.assertIn("Import Preview (dji-air-2)", out)
        self.assertIn("DJI-MICS", out)
        self.assertIn("DJI-DRONES", out)
        self.assertEqual(out.count("Disk space at dest:"), 1)
        self.assertIn("(dry run — nothing executed)", out)


if __name__ == "__main__":
    unittest.main()
