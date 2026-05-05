"""Chain-detection tests against the §3 detection rule."""

import unittest
from datetime import datetime
from pathlib import Path

from _load_module import load

dji = load()


def _clip(tx: str, idx: int, start: str, version: str, duration_s: float):
    """Build a Clip with a synthetic Wav."""
    wav = dji.Wav(
        fmt_code=3, channels=2, sample_rate=48000,
        block_align=8, bits_per_sample=32,
        data_offset=0, data_size=int(duration_s * 48000) * 8,
    )
    return dji.Clip(
        path=Path(f"/tmp/{tx}_MIC{idx:03d}_{start}_{version}.wav"),
        tx=tx, clip_idx=idx,
        start=datetime.strptime(start, "%Y%m%d_%H%M%S"),
        version=version, wav=wav,
        volume=Path("/Volumes/test"),
    )


class TestBuildChains(unittest.TestCase):

    def test_two_30min_files_become_one_chain(self):
        clips = [
            _clip("TX01", 1, "20260502_110930", "edit", 1800.045),
            _clip("TX01", 2, "20260502_113930", "edit", 600.0),
        ]
        chains = dji.build_chains(clips)
        self.assertEqual(len(chains), 1)
        self.assertEqual(len(chains[0].clips), 2)
        self.assertFalse(chains[0].is_singleton)

    def test_short_clips_with_small_gap_are_NOT_joined(self):
        # Manual pause/resume — must not join.
        clips = [
            _clip("TX01", 1, "20260502_110930", "edit", 30.0),
            _clip("TX01", 2, "20260502_111002", "edit", 60.0),  # 2s after end
        ]
        chains = dji.build_chains(clips)
        self.assertEqual(len(chains), 2)  # both are singletons
        for c in chains:
            self.assertTrue(c.is_singleton)

    def test_long_chain_of_4_pieces(self):
        clips = [
            _clip("TX02", 7, "20260502_110930", "orig", 1800.045),
            _clip("TX02", 8, "20260502_113930", "orig", 1800.045),
            _clip("TX02", 9, "20260502_120930", "orig", 1800.045),
            _clip("TX02", 10, "20260502_123930", "orig", 600.0),  # tail
        ]
        chains = dji.build_chains(clips)
        self.assertEqual(len(chains), 1)
        self.assertEqual(len(chains[0].clips), 4)
        self.assertEqual(chains[0].tx, "TX02")

    def test_break_when_gap_too_large(self):
        # 30-min duration but next clip is 10s later → not auto-split
        clips = [
            _clip("TX01", 1, "20260502_110930", "edit", 1800.045),
            _clip("TX01", 2, "20260502_113940", "edit", 1800.045),  # 10s gap
        ]
        chains = dji.build_chains(clips)
        self.assertEqual(len(chains), 2)

    def test_separate_groups_per_tx_and_version(self):
        clips = [
            _clip("TX01", 1, "20260502_110930", "edit", 1800.045),
            _clip("TX01", 2, "20260502_113930", "edit", 600.0),
            _clip("TX02", 1, "20260502_110930", "edit", 1800.045),
            _clip("TX02", 2, "20260502_113930", "edit", 600.0),
            _clip("TX01", 1, "20260502_110930", "orig", 1800.045),
            _clip("TX01", 2, "20260502_113930", "orig", 600.0),
        ]
        chains = dji.build_chains(clips)
        self.assertEqual(len(chains), 3)
        for c in chains:
            self.assertFalse(c.is_singleton)
            self.assertEqual(len(c.clips), 2)

    def test_single_clip_is_singleton(self):
        clips = [_clip("TX01", 1, "20260502_110930", "edit", 60.0)]
        chains = dji.build_chains(clips)
        self.assertEqual(len(chains), 1)
        self.assertTrue(chains[0].is_singleton)

    def test_filename_rounding_minus_45ms_is_treated_as_adjacent(self):
        # Real DJI shape: file 1 ends at +45ms past the second; file 2's
        # filename rounds to that second, so nominal gap is -45ms.
        clips = [
            _clip("TX02", 7, "20260502_110930", "orig", 1800.045),
            _clip("TX02", 8, "20260502_113930", "orig", 1800.045),  # filename @ 11:39:30
        ]
        chains = dji.build_chains(clips)
        self.assertEqual(len(chains), 1)
        self.assertEqual(len(chains[0].clips), 2)


class TestOverlapMeasurement(unittest.TestCase):

    def test_overlap_via_synthetic_files(self):
        # Build two WAV files where file2's first 2400 frames are byte-identical
        # to file1's last 2400 frames (50ms at 48kHz).
        import struct
        import tempfile

        def make_wav(path: Path, samples_left: list[float], samples_right: list[float]):
            channels = 2
            sample_rate = 48000
            bits = 32
            block_align = channels * (bits // 8)
            n = len(samples_left)
            data_size = n * block_align
            fmt = struct.pack("<HHIIHH", 3, channels, sample_rate,
                              sample_rate * block_align, block_align, bits)
            with open(path, "wb") as f:
                f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + data_size) + b"WAVE")
                f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
                f.write(b"data" + struct.pack("<I", data_size))
                for L, R in zip(samples_left, samples_right):
                    f.write(struct.pack("<ff", L, R))

        with tempfile.TemporaryDirectory() as td:
            n1 = 4800   # 100ms
            n_overlap = 2400  # 50ms
            n2 = 4800   # 100ms

            # Generate distinct random-ish samples
            left_a = [(i % 17) / 17.0 for i in range(n1)]
            right_a = [(i % 23) / 23.0 for i in range(n1)]
            # File 2 starts with the LAST n_overlap samples of file 1, then
            # diverges.
            left_b_overlap = left_a[-n_overlap:]
            right_b_overlap = right_a[-n_overlap:]
            left_b_rest = [(i % 31) / 31.0 + 0.05 for i in range(n2 - n_overlap)]
            right_b_rest = [(i % 37) / 37.0 + 0.05 for i in range(n2 - n_overlap)]

            p1 = Path(td) / "a.wav"
            p2 = Path(td) / "b.wav"
            make_wav(p1, left_a, right_a)
            make_wav(p2, left_b_overlap + left_b_rest, right_b_overlap + right_b_rest)

            w1 = dji.parse_wav_header(p1)
            w2 = dji.parse_wav_header(p2)
            k = dji.measure_overlap_frames(p1, w1, p2, w2, probe_s=0.5)
            self.assertEqual(k, n_overlap,
                             f"expected {n_overlap} frames overlap, got {k}")

    def test_no_overlap_returns_zero(self):
        import struct
        import tempfile

        def make_wav(path: Path, samples_left: list[float], samples_right: list[float]):
            channels = 2
            sample_rate = 48000
            bits = 32
            block_align = channels * (bits // 8)
            n = len(samples_left)
            data_size = n * block_align
            fmt = struct.pack("<HHIIHH", 3, channels, sample_rate,
                              sample_rate * block_align, block_align, bits)
            with open(path, "wb") as f:
                f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + data_size) + b"WAVE")
                f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
                f.write(b"data" + struct.pack("<I", data_size))
                for L, R in zip(samples_left, samples_right):
                    f.write(struct.pack("<ff", L, R))

        with tempfile.TemporaryDirectory() as td:
            n = 4800
            left_a = [(i % 17) / 17.0 for i in range(n)]
            right_a = [(i % 23) / 23.0 for i in range(n)]
            left_b = [((i + 1000) % 19) / 19.0 + 0.5 for i in range(n)]
            right_b = [((i + 1000) % 29) / 29.0 + 0.5 for i in range(n)]

            p1 = Path(td) / "a.wav"
            p2 = Path(td) / "b.wav"
            make_wav(p1, left_a, right_a)
            make_wav(p2, left_b, right_b)

            w1 = dji.parse_wav_header(p1)
            w2 = dji.parse_wav_header(p2)
            k = dji.measure_overlap_frames(p1, w1, p2, w2, probe_s=0.5)
            self.assertEqual(k, 0)


if __name__ == "__main__":
    unittest.main()
