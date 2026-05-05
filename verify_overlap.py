#!/usr/bin/env python3
"""
Probe DJI mic files for split-overlap behavior.

DJI records 32-bit float WAV (format code 3), which stdlib `wave` rejects,
so we parse the RIFF chunks manually.
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
ADJACENT_TOLERANCE_S = 10.0


@dataclass
class Wav:
    fmt_code: int       # 1=PCM, 3=IEEE float
    channels: int
    sample_rate: int
    byte_rate: int
    block_align: int
    bits_per_sample: int
    data_offset: int    # byte offset of `data` chunk payload
    data_size: int      # bytes of audio data

    @property
    def bytes_per_sample(self) -> int:
        return self.bits_per_sample // 8

    @property
    def nframes(self) -> int:
        if self.block_align == 0:
            return 0
        return self.data_size // self.block_align

    @property
    def duration_s(self) -> float:
        return self.nframes / self.sample_rate if self.sample_rate else 0.0


def parse_wav_header(path: Path) -> Wav | None:
    """Walk RIFF chunks, return Wav metadata. Tolerant to extra chunks."""
    try:
        with open(path, "rb") as f:
            riff = f.read(12)
            if len(riff) < 12 or riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
                return None
            fmt_code = channels = sample_rate = byte_rate = 0
            block_align = bits_per_sample = 0
            data_offset = data_size = 0
            while True:
                hdr = f.read(8)
                if len(hdr) < 8:
                    break
                cid, csize = struct.unpack("<4sI", hdr)
                start = f.tell()
                if cid == b"fmt ":
                    fmt_data = f.read(csize)
                    (fmt_code, channels, sample_rate, byte_rate,
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
            return Wav(fmt_code, channels, sample_rate, byte_rate, block_align,
                       bits_per_sample, data_offset, data_size)
    except OSError as e:
        print(f"  warn: {path.name}: {e}", file=sys.stderr)
        return None


def read_mono_window(path: Path, wav: Wav, frame_offset: int, frame_count: int) -> list[float]:
    """Read frames as mono floats (downmix by averaging channels)."""
    if frame_count <= 0:
        return []
    frame_offset = max(0, min(frame_offset, wav.nframes))
    frame_count = max(0, min(frame_count, wav.nframes - frame_offset))
    if frame_count == 0:
        return []
    byte_offset = wav.data_offset + frame_offset * wav.block_align
    byte_count = frame_count * wav.block_align
    with open(path, "rb") as f:
        f.seek(byte_offset)
        raw = f.read(byte_count)
    bps = wav.bytes_per_sample
    ch = wav.channels
    n = len(raw) // wav.block_align
    if wav.fmt_code == 3 and bps == 4:  # float32
        vals = struct.unpack(f"<{n * ch}f", raw[: n * wav.block_align])
    elif wav.fmt_code == 1 and bps == 2:  # int16
        ints = struct.unpack(f"<{n * ch}h", raw[: n * wav.block_align])
        vals = [v / 32768.0 for v in ints]
    elif wav.fmt_code == 1 and bps == 3:  # int24
        vals = []
        for i in range(n * ch):
            b = raw[i * 3 : i * 3 + 3]
            v = int.from_bytes(b, "little", signed=True)
            vals.append(v / (1 << 23))
    else:
        return []
    if ch == 1:
        return list(vals)
    out: list[float] = []
    for i in range(0, len(vals), ch):
        chunk = vals[i : i + ch]
        if len(chunk) < ch:
            break
        out.append(sum(chunk) / ch)
    return out


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
    skipped = 0
    for vol in VOLUMES:
        if not vol.exists():
            continue
        for p in vol.rglob("*.wav"):
            m = PATTERN.search(p.name)
            if not m:
                continue
            wav = parse_wav_header(p)
            if wav is None:
                skipped += 1
                continue
            clips.append(Clip(
                path=p,
                tx=f"TX{m.group(1)}",
                clip_idx=int(m.group(2)),
                start=datetime.strptime(m.group(3) + m.group(4), "%Y%m%d%H%M%S"),
                version=m.group(5),
                wav=wav,
            ))
    if skipped:
        print(f"  (skipped {skipped} unparseable files)")
    return clips


def normalized_xcorr(a: list[float], b: list[float], max_lag: int) -> tuple[int, float]:
    if not a or not b:
        return (0, 0.0)
    n = min(len(a), len(b))
    a = a[:n]
    b = b[:n]
    ma = sum(a) / n
    mb = sum(b) / n
    ax = [x - ma for x in a]
    bx = [x - mb for x in b]
    norm_a = sum(x * x for x in ax) ** 0.5
    norm_b = sum(x * x for x in bx) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return (0, 0.0)
    best_score = -2.0
    best_lag = 0
    for lag in range(-max_lag, max_lag + 1):
        s = 0.0
        if lag >= 0:
            count = n - lag
            for i in range(count):
                s += ax[i + lag] * bx[i]
        else:
            count = n + lag
            for i in range(count):
                s += ax[i] * bx[i - lag]
        score = s / (norm_a * norm_b)
        if score > best_score:
            best_score = score
            best_lag = lag
    return (best_lag, best_score)


def main() -> int:
    clips = discover()
    print(f"discovered {len(clips)} parseable clips\n")
    if not clips:
        return 1

    # Show one sample header for sanity
    sample = clips[0].wav
    print(f"sample format: fmt_code={sample.fmt_code} ch={sample.channels} "
          f"sr={sample.sample_rate} bps={sample.bits_per_sample} "
          f"(fmt 3 = IEEE float, 1 = PCM)\n")

    groups: dict[tuple[str, str], list[Clip]] = {}
    for c in clips:
        groups.setdefault((c.tx, c.version), []).append(c)

    overlap_evidence = 0
    clean_cut_evidence = 0
    gap_evidence = 0
    pair_count = 0

    for (tx, version), gclips in sorted(groups.items()):
        gclips.sort(key=lambda c: c.start)
        print(f"=== {tx} / {version}: {len(gclips)} clips ===")
        candidate_idxs = []
        for i in range(len(gclips) - 1):
            a, b = gclips[i], gclips[i + 1]
            gap = (b.start - a.end).total_seconds()
            if abs(gap) <= ADJACENT_TOLERANCE_S:
                candidate_idxs.append(i)
        if not candidate_idxs:
            print("  (no adjacent pairs within tolerance)\n")
            continue

        for i in candidate_idxs:
            a, b = gclips[i], gclips[i + 1]
            gap = (b.start - a.end).total_seconds()
            print(f"  [{a.path.name}]  end={a.end.time()}  dur={a.wav.duration_s:.3f}s")
            print(f"  [{b.path.name}]  start={b.start.time()}  gap={gap:+.3f}s")

            if (a.wav.sample_rate != b.wav.sample_rate or
                    a.wav.channels != b.wav.channels or
                    a.wav.bits_per_sample != b.wav.bits_per_sample):
                print("    skip xcorr: format mismatch\n")
                continue
            pair_count += 1

            # Compare last 200ms of `a` against first 200ms of `b`
            window_ms = 200
            window_frames = int(a.wav.sample_rate * window_ms / 1000)
            tail = read_mono_window(a.path, a.wav, a.wav.nframes - window_frames, window_frames)
            head = read_mono_window(b.path, b.wav, 0, window_frames)
            max_lag = int(a.wav.sample_rate * 50 / 1000)  # ±50ms

            lag, score = normalized_xcorr(tail, head, max_lag)
            lag_ms = lag * 1000.0 / a.wav.sample_rate

            if score > 0.95 and abs(lag_ms) < 5:
                verdict = "OVERLAP — head matches tail at zero lag"
                overlap_evidence += 1
            elif score > 0.7:
                verdict = f"PARTIAL OVERLAP — best score {score:.3f} at lag {lag_ms:+.2f}ms"
                overlap_evidence += 1
            elif score < 0.3:
                if abs(gap) < 0.05:
                    verdict = f"CLEAN CUT — no correlation, gap {gap:+.3f}s"
                    clean_cut_evidence += 1
                else:
                    verdict = f"GAP — separate audio, {gap:+.3f}s apart"
                    gap_evidence += 1
            else:
                verdict = f"INCONCLUSIVE — score {score:.3f}, lag {lag_ms:+.2f}ms"
            print(f"    xcorr: {verdict}\n")

    print("--- summary ---")
    print(f"adjacent pairs analyzed:  {pair_count}")
    print(f"overlap evidence:         {overlap_evidence}")
    print(f"clean-cut evidence:       {clean_cut_evidence}")
    print(f"gap evidence:             {gap_evidence}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
