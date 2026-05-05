#!/usr/bin/env python3
"""
v3: definitive byte-exact overlap test.

The xcorr approach is statistical and suffers from spurious high scores
when content has similar but non-identical structure (e.g. same speaker
continuing speech). Drop it for the canonical question.

Definitive test: read the raw audio data from the data chunk of each WAV.
If file N+1 begins where file N continues (i.e., they share audio
samples at the boundary), then there exists some K > 0 such that
  N.data[-K:] == N1.data[:K]
exactly, byte-for-byte.

For each auto-split candidate pair, find the maximum such K. If K is
zero across all pairs, splits are sample-accurate clean cuts. If K is
nonzero and consistent, that's the systematic overlap value.
"""

from __future__ import annotations

import re
import struct
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

VOLUMES = [Path("/Volumes/NO NAME"), Path("/Volumes/NO NAME 1")]
PATTERN = re.compile(r"TX(\d+)_MIC(\d+)_(\d{8})_(\d{6})_(edit|orig)\.wav$")
ADJACENT_TOLERANCE_S = 2.0
DURATION_AUTOSPLIT_LO = 1799.5
DURATION_AUTOSPLIT_HI = 1800.5
PROBE_S = 30.0  # check overlap up to 30 seconds


@dataclass
class Wav:
    fmt_code: int
    channels: int
    sample_rate: int
    block_align: int
    bits_per_sample: int
    data_offset: int
    data_size: int

    @property
    def nframes(self) -> int:
        return self.data_size // self.block_align if self.block_align else 0

    @property
    def duration_s(self) -> float:
        return self.nframes / self.sample_rate if self.sample_rate else 0.0


def parse_wav_header(path: Path) -> Wav | None:
    try:
        with open(path, "rb") as f:
            riff = f.read(12)
            if len(riff) < 12 or riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
                return None
            fmt_code = channels = sample_rate = block_align = bits_per_sample = 0
            data_offset = data_size = 0
            while True:
                hdr = f.read(8)
                if len(hdr) < 8:
                    break
                cid, csize = struct.unpack("<4sI", hdr)
                start = f.tell()
                if cid == b"fmt ":
                    fmt_data = f.read(csize)
                    (fmt_code, channels, sample_rate, _byte_rate,
                     block_align, bits_per_sample) = struct.unpack(
                        "<HHIIHH", fmt_data[:16]
                    )
                elif cid == b"data":
                    data_offset = start
                    data_size = csize
                    break
                else:
                    f.seek(start + csize + (csize & 1))
                    continue
                f.seek(start + csize + (csize & 1))
            if not (sample_rate and bits_per_sample and data_size):
                return None
            return Wav(fmt_code, channels, sample_rate, block_align,
                       bits_per_sample, data_offset, data_size)
    except OSError:
        return None


def read_data_window_bytes(path: Path, wav: Wav, offset_frames: int, count_frames: int) -> bytes:
    if count_frames <= 0:
        return b""
    offset_frames = max(0, min(offset_frames, wav.nframes))
    count_frames = max(0, min(count_frames, wav.nframes - offset_frames))
    if count_frames == 0:
        return b""
    byte_offset = wav.data_offset + offset_frames * wav.block_align
    byte_count = count_frames * wav.block_align
    with open(path, "rb") as f:
        f.seek(byte_offset)
        return f.read(byte_count)


def longest_overlap_frames(tail: bytes, head: bytes, block_align: int) -> int:
    """Return the largest K (in frames) such that tail[-K*ba:] == head[:K*ba]."""
    if not tail or not head or block_align == 0:
        return 0
    max_k = min(len(tail), len(head)) // block_align
    if max_k == 0:
        return 0
    # Walk K from largest to smallest. Use Python slice equality (memcmp under the hood).
    # Linear scan is O(max_k * frame_size) which is fine for max_k ~ 96000 frames.
    for k in range(max_k, 0, -1):
        size = k * block_align
        if tail[-size:] == head[:size]:
            return k
    return 0


@dataclass
class Clip:
    path: Path
    tx: str
    clip_idx: int
    start: datetime
    version: str
    wav: Wav

    @property
    def end(self) -> datetime:
        return self.start + timedelta(seconds=self.wav.duration_s)


def discover() -> list[Clip]:
    clips: list[Clip] = []
    for vol in VOLUMES:
        if not vol.exists():
            continue
        for p in vol.rglob("*.wav"):
            m = PATTERN.search(p.name)
            if not m:
                continue
            wav = parse_wav_header(p)
            if wav is None:
                continue
            clips.append(Clip(
                path=p,
                tx=f"TX{m.group(1)}",
                clip_idx=int(m.group(2)),
                start=datetime.strptime(m.group(3) + m.group(4), "%Y%m%d%H%M%S"),
                version=m.group(5),
                wav=wav,
            ))
    return clips


def main() -> int:
    clips = discover()
    print(f"discovered {len(clips)} clips\n")
    if not clips:
        return 1

    groups: dict[tuple[str, str], list[Clip]] = {}
    for c in clips:
        groups.setdefault((c.tx, c.version), []).append(c)
    for g in groups.values():
        g.sort(key=lambda c: c.start)

    autosplit_pairs: list[tuple[Clip, Clip]] = []
    other_adjacent: list[tuple[Clip, Clip, float]] = []  # for sanity check
    for gclips in groups.values():
        for i in range(len(gclips) - 1):
            a, b = gclips[i], gclips[i + 1]
            gap = (b.start - a.end).total_seconds()
            if abs(gap) > ADJACENT_TOLERANCE_S:
                continue
            if DURATION_AUTOSPLIT_LO <= a.wav.duration_s <= DURATION_AUTOSPLIT_HI:
                autosplit_pairs.append((a, b))
            else:
                other_adjacent.append((a, b, gap))

    print(f"auto-split candidate pairs: {len(autosplit_pairs)}")
    print(f"other adjacent (non-autosplit duration): {len(other_adjacent)}\n")

    # Definitive byte-exact overlap test.
    print(f"=== byte-exact overlap test (probe size: {PROBE_S}s) ===\n")
    overlap_frame_counts = []
    for a, b in autosplit_pairs:
        if (a.wav.sample_rate != b.wav.sample_rate or
                a.wav.block_align != b.wav.block_align or
                a.wav.fmt_code != b.wav.fmt_code):
            print(f"  skip: format mismatch {a.path.name} → {b.path.name}")
            continue

        sr = a.wav.sample_rate
        ba = a.wav.block_align
        probe_frames = int(sr * PROBE_S)
        tail = read_data_window_bytes(a.path, a.wav, max(0, a.wav.nframes - probe_frames), probe_frames)
        head = read_data_window_bytes(b.path, b.wav, 0, probe_frames)
        k = longest_overlap_frames(tail, head, ba)
        overlap_ms = k / sr * 1000.0
        overlap_frame_counts.append(k)
        print(f"  {a.tx}/{a.version}  {a.path.name}  →  {b.path.name}")
        print(f"      overlap: {k} frames  ({overlap_ms:.3f} ms)")

    print()
    print("=== summary ===")
    print(f"  pairs analyzed: {len(overlap_frame_counts)}")
    if overlap_frame_counts:
        unique = sorted(set(overlap_frame_counts))
        print(f"  unique overlap-frame values: {unique}")
        if all(k == 0 for k in overlap_frame_counts):
            print(f"  → CLEAN CUT confirmed: zero byte-overlap on every pair.")
            print(f"  → ffmpeg -c copy concat is sample-accurate.")
        elif all(k == overlap_frame_counts[0] for k in overlap_frame_counts):
            k = overlap_frame_counts[0]
            print(f"  → SYSTEMATIC OVERLAP: {k} frames ({k / 48000 * 1000:.3f} ms at 48kHz)")
            print(f"  → Join must trim {k} leading frames from each non-first chain member.")
        else:
            print(f"  → VARIABLE OVERLAP: needs per-pair handling.")

    # Sanity: also test a few adjacent-but-non-autosplit pairs to make sure
    # the test would actually find overlap if it existed (same-format).
    print()
    print("=== sanity: short adjacent pairs (manual restarts, expect 0) ===")
    for a, b, gap in other_adjacent[:10]:
        if (a.wav.sample_rate != b.wav.sample_rate or
                a.wav.block_align != b.wav.block_align or
                a.wav.fmt_code != b.wav.fmt_code):
            continue
        sr = a.wav.sample_rate
        ba = a.wav.block_align
        probe_frames = int(sr * PROBE_S)
        tail = read_data_window_bytes(a.path, a.wav, max(0, a.wav.nframes - probe_frames), probe_frames)
        head = read_data_window_bytes(b.path, b.wav, 0, probe_frames)
        k = longest_overlap_frames(tail, head, ba)
        print(f"  gap={gap:+.3f}s  overlap={k} frames  {a.path.name[:40]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
