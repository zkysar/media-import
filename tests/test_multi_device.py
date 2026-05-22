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


class EmptyAfterFilterTest(unittest.TestCase):
    def setUp(self):
        self._orig_find = m.find_all_volumes
        self._orig_validate = m.validate_runtime
        self._orig_dd = m.DJI_AIR_2.detect
        self._orig_disc = m.DJI_AIR_2.discover
        m.validate_runtime = lambda: None

    def tearDown(self):
        m.find_all_volumes = self._orig_find
        m.validate_runtime = self._orig_validate
        m.DJI_AIR_2.detect = self._orig_dd
        m.DJI_AIR_2.discover = self._orig_disc

    def test_all_items_filtered_out_returns_0_no_media(self):
        drone_vol = Path("/Volumes/DRONE")
        # Capture dated 2026-05-03. Today is 2026-05-22 so --days 1 sets
        # from_date=2026-05-21; dji_air_filter_by_args drops this group.
        drone_g = m.MediaGroup(
            kind="video",
            primary=drone_vol / "DCIM/100MEDIA/DJI_0001.MP4",
            files=[drone_vol / "DCIM/100MEDIA/DJI_0001.MP4"],
            timestamp=datetime(2026, 5, 3, 10, 0, 0),
            body_serial="UNKNOWN", size_bytes=2000, volume=drone_vol)
        m.find_all_volumes = lambda: [drone_vol]
        m.DJI_AIR_2.detect = lambda v: v == drone_vol
        m.DJI_AIR_2.discover = lambda vols: [drone_g]

        with tempfile.TemporaryDirectory() as tmp:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = m.main(["--dest", tmp, "--device", "auto",
                             "--days", "1", "--yes", "--dry-run"])
            stderr = err.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("no media matched the given filters", stderr)


class TwoDeviceExecutionTest(unittest.TestCase):
    """Drive main() through Phase 7 (real execution, no --dry-run) for mic +
    drone. Asserts both devices' files land under the dest tree and that the
    Done/Singletons summary prints."""

    def setUp(self):
        self._orig = {
            "find": m.find_all_volumes,
            "validate": m.validate_runtime,
            "mic_detect": m.DJI_MIC.detect,
            "mic_disc": m.DJI_MIC.discover,
            "drone_detect": m.DJI_AIR_2.detect,
            "drone_disc": m.DJI_AIR_2.discover,
        }
        m.validate_runtime = lambda: None

    def tearDown(self):
        m.find_all_volumes = self._orig["find"]
        m.validate_runtime = self._orig["validate"]
        m.DJI_MIC.detect = self._orig["mic_detect"]
        m.DJI_MIC.discover = self._orig["mic_disc"]
        m.DJI_AIR_2.detect = self._orig["drone_detect"]
        m.DJI_AIR_2.discover = self._orig["drone_disc"]

    def test_real_execution_both_devices_files_land(self):
        with tempfile.TemporaryDirectory() as srcdir:
            src = Path(srcdir)

            # --- Mic source file ---
            # A real .wav file is required: Clip.size_bytes stats the path,
            # and run_copies does shutil.copy2(src, staging).
            # We write a minimal valid WAV (44-byte header + silence) so
            # the file exists and has non-zero size.
            mic_vol = src / "MIC"
            mic_vol.mkdir()
            mic_fname = "TX01_MIC001_20260503_120000_orig.wav"
            mic_src = mic_vol / mic_fname
            # 44-byte PCM WAV header for 1 second of mono 16-bit 8000 Hz silence.
            import struct
            sample_rate, channels, bits = 8000, 1, 16
            n_samples = sample_rate  # 1 second
            data_size = n_samples * channels * (bits // 8)
            block_align = channels * (bits // 8)
            byte_rate = sample_rate * block_align
            header = struct.pack(
                "<4sI4s4sIHHIIHH4sI",
                b"RIFF", 36 + data_size, b"WAVE",
                b"fmt ", 16, 1, channels, sample_rate, byte_rate,
                block_align, bits,
                b"data", data_size,
            )
            mic_src.write_bytes(header + bytes(data_size))

            # Clip fields: path, tx, clip_idx, start, version, wav, volume.
            # Wav: fmt_code, channels, sample_rate, block_align, bits_per_sample,
            #      data_offset, data_size.
            clip = m.Clip(
                path=mic_src,
                tx="TX01", clip_idx=1,
                start=datetime(2026, 5, 3, 12, 0, 0),
                version="orig",
                wav=m.Wav(1, channels, sample_rate, block_align, bits, 44, data_size),
                volume=mic_vol)

            # --- Drone source file ---
            # dji_air_build_plan stats each src file; run_copies does shutil.copy2.
            drone_vol = src / "DRONE"
            drone_media = drone_vol / "DCIM" / "100MEDIA"
            drone_media.mkdir(parents=True)
            drone_fname = "DJI_0001.MP4"
            drone_src = drone_media / drone_fname
            drone_src.write_bytes(b"\x00" * 1024)

            drone_g = m.MediaGroup(
                kind="video",
                primary=drone_src,
                files=[drone_src],
                timestamp=datetime(2026, 5, 3, 10, 0, 0),
                body_serial="UNKNOWN", size_bytes=1024, volume=drone_vol)

            m.find_all_volumes = lambda: [mic_vol, drone_vol]
            m.DJI_MIC.detect = lambda v: v == mic_vol
            m.DJI_MIC.discover = lambda vols: [clip]
            m.DJI_AIR_2.detect = lambda v: v == drone_vol
            m.DJI_AIR_2.discover = lambda vols: [drone_g]

            with tempfile.TemporaryDirectory() as dest:
                dest_path = Path(dest)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    rc = m.main(["--dest", dest, "--device", "auto",
                                 "--days", "3650", "--yes"])
                stdout = out.getvalue()

                # rc == 0 means Phase 7 completed without error.
                self.assertEqual(rc, 0)

                # Mic singleton: <dest>/RAW/2026-05-03/DJI-MICS/TX01/ORIG/<fname>
                # Confirmed by dest_dir_for(dest, date(2026,5,3), "TX01", "orig")
                # → dest/RAW/2026-05-03/DJI-MICS/TX01/ORIG/
                mic_out = dest_path / "RAW" / "2026-05-03" / "DJI-MICS" / "TX01" / "ORIG" / mic_fname
                self.assertTrue(mic_out.exists(), f"Mic output missing: {mic_out}")

                # Drone video: <dest>/RAW/2026-05-03/DJI-DRONES/VIDEOS/<fname>
                # Confirmed by _dji_air_dest_dir_for(dest, date(2026,5,3), "video")
                # → dest/RAW/2026-05-03/DJI-DRONES/VIDEOS/
                drone_out = dest_path / "RAW" / "2026-05-03" / "DJI-DRONES" / "VIDEOS" / drone_fname
                self.assertTrue(drone_out.exists(), f"Drone output missing: {drone_out}")

                # Summary line from main() phase 7 output.
                self.assertIn("Done in", stdout)
                self.assertIn("Singletons:", stdout)


if __name__ == "__main__":
    unittest.main()
