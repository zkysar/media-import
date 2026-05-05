"""WAV header parsing tests, including the DJI 32-bit float case."""

import struct
import tempfile
import unittest
from pathlib import Path

from _load_module import load

dji = load()


def _write_wav(path: Path, fmt_code: int, channels: int, sample_rate: int,
               bits_per_sample: int, n_frames: int,
               extra_chunk_before_data: bytes = b"") -> None:
    block_align = channels * (bits_per_sample // 8)
    byte_rate = sample_rate * block_align
    data_size = n_frames * block_align
    fmt_chunk = struct.pack("<HHIIHH",
                            fmt_code, channels, sample_rate,
                            byte_rate, block_align, bits_per_sample)
    fmt_size = len(fmt_chunk)
    extra_total = (8 + len(extra_chunk_before_data)) if extra_chunk_before_data else 0
    riff_size = 4 + (8 + fmt_size) + extra_total + (8 + data_size)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", riff_size) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", fmt_size) + fmt_chunk)
        if extra_chunk_before_data:
            f.write(b"junk" + struct.pack("<I", len(extra_chunk_before_data))
                    + extra_chunk_before_data)
        f.write(b"data" + struct.pack("<I", data_size))
        f.write(b"\x00" * data_size)


class TestParseWavHeader(unittest.TestCase):

    def test_dji_float32_stereo_48k(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.wav"
            _write_wav(p, fmt_code=3, channels=2, sample_rate=48000,
                       bits_per_sample=32, n_frames=4800)
            wav = dji.parse_wav_header(p)
            self.assertIsNotNone(wav)
            self.assertEqual(wav.fmt_code, 3)
            self.assertEqual(wav.channels, 2)
            self.assertEqual(wav.sample_rate, 48000)
            self.assertEqual(wav.bits_per_sample, 32)
            self.assertEqual(wav.block_align, 8)
            self.assertEqual(wav.nframes, 4800)
            self.assertAlmostEqual(wav.duration_s, 0.1, places=4)

    def test_pcm16_mono_44k(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "b.wav"
            _write_wav(p, fmt_code=1, channels=1, sample_rate=44100,
                       bits_per_sample=16, n_frames=44100)
            wav = dji.parse_wav_header(p)
            self.assertIsNotNone(wav)
            self.assertEqual(wav.fmt_code, 1)
            self.assertEqual(wav.bits_per_sample, 16)
            self.assertEqual(wav.nframes, 44100)
            self.assertAlmostEqual(wav.duration_s, 1.0, places=4)

    def test_skips_unknown_chunks_before_data(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.wav"
            _write_wav(p, fmt_code=3, channels=2, sample_rate=48000,
                       bits_per_sample=32, n_frames=1000,
                       extra_chunk_before_data=b"x" * 16)
            wav = dji.parse_wav_header(p)
            self.assertIsNotNone(wav)
            self.assertEqual(wav.nframes, 1000)

    def test_returns_none_on_non_riff(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "d.wav"
            p.write_bytes(b"NOT-A-WAV")
            wav = dji.parse_wav_header(p)
            self.assertIsNone(wav)


if __name__ == "__main__":
    unittest.main()
