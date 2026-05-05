"""Test that overlap measurement returns 0 for silent regions.

This was a real bug discovered during smoke testing: TX01 chain files were
pure silence, and the byte-equality test trivially "matched" arbitrary-sized
windows of zeros. The fix is a silence guard after the binary search.
"""

import struct
import tempfile
import unittest
from pathlib import Path

from _load_module import load

dji = load()


def _write_float32_mono_wav(path: Path, samples: list[float], sample_rate: int = 48000) -> None:
    n = len(samples)
    block_align = 4
    data_size = n * block_align
    fmt = struct.pack("<HHIIHH", 3, 1, sample_rate,
                      sample_rate * block_align, block_align, 32)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + data_size) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", data_size))
        for s in samples:
            f.write(struct.pack("<f", s))


class TestSilenceGuard(unittest.TestCase):

    def test_silent_files_report_zero_overlap(self):
        with tempfile.TemporaryDirectory() as td:
            n = 4800
            silent = [0.0] * n
            p1 = Path(td) / "a.wav"
            p2 = Path(td) / "b.wav"
            _write_float32_mono_wav(p1, silent)
            _write_float32_mono_wav(p2, silent)

            w1 = dji.parse_wav_header(p1)
            w2 = dji.parse_wav_header(p2)
            k = dji.measure_overlap_frames(p1, w1, p2, w2, probe_s=0.05)
            self.assertEqual(k, 0,
                             f"silent files must report 0 overlap, got {k}")

    def test_real_overlap_still_detected(self):
        # Mostly silent, but with a brief tone in the overlap region.
        with tempfile.TemporaryDirectory() as td:
            n_total = 9600  # 200ms
            n_overlap = 2400  # 50ms
            # File 1: silence, then 50ms of signal
            file1 = [0.0] * (n_total - n_overlap) + [0.5] * n_overlap
            # File 2: same 50ms signal, then more silence
            file2 = [0.5] * n_overlap + [0.0] * (n_total - n_overlap)
            p1 = Path(td) / "a.wav"
            p2 = Path(td) / "b.wav"
            _write_float32_mono_wav(p1, file1)
            _write_float32_mono_wav(p2, file2)

            w1 = dji.parse_wav_header(p1)
            w2 = dji.parse_wav_header(p2)
            k = dji.measure_overlap_frames(p1, w1, p2, w2, probe_s=0.5)
            self.assertEqual(k, n_overlap,
                             f"expected {n_overlap} frames overlap, got {k}")


if __name__ == "__main__":
    unittest.main()
