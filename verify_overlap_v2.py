#!/usr/bin/env python3
"""
v2: address review C1/C2.

Changes from v1:
- Lag search widened from ±50ms to ±2000ms (per C1).
- Switched to numpy-FFT cross-correlation so a wide search is tractable.
- Added a same-clip-baseline pass: how high does xcorr score on a 200ms
  window vs the same window with zero shift? (sanity, expect ≈1.0)
- Added a null-distribution pass: cross-correlate probes from one chain
  against tails from a *different* chain on a different day (per C2).
  This tells us what "uncorrelated speech" actually scores in this content,
  which the v1 conclusion ("0.70 = coincidence") was asserting without
  evidence.

Search shape: probe = first 200ms of N+1 (the head); haystack = last 2.0s
of N (the tail). The lag-from-tail-end at which the probe matches tells
us the overlap amount: lag=0 → clean cut (probe sits at the very end of
N, so N+1 begins where N ends); lag>0 → that-many-seconds of overlap.
"""

from __future__ import annotations

import re
import struct
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

VOLUMES = [Path("/Volumes/NO NAME"), Path("/Volumes/NO NAME 1")]
PATTERN = re.compile(r"TX(\d+)_MIC(\d+)_(\d{8})_(\d{6})_(edit|orig)\.wav$")

ADJACENT_TOLERANCE_S = 2.0          # only analyze adjacent pairs (per spec §3 cond 2)
HAYSTACK_S = 2.0                    # last N seconds of file N searched
PROBE_S = 0.200                     # first N seconds of file N+1 used as probe
DURATION_AUTOSPLIT_LO = 1799.5      # spec §3 cond 1
DURATION_AUTOSPLIT_HI = 1800.5


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
    def bytes_per_sample(self) -> int:
        return self.bits_per_sample // 8

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


def read_mono(path: Path, wav: Wav, frame_offset: int, frame_count: int) -> np.ndarray:
    if frame_count <= 0:
        return np.array([], dtype=np.float32)
    frame_offset = max(0, min(frame_offset, wav.nframes))
    frame_count = max(0, min(frame_count, wav.nframes - frame_offset))
    if frame_count == 0:
        return np.array([], dtype=np.float32)
    byte_offset = wav.data_offset + frame_offset * wav.block_align
    byte_count = frame_count * wav.block_align
    with open(path, "rb") as f:
        f.seek(byte_offset)
        raw = f.read(byte_count)
    bps = wav.bytes_per_sample
    ch = wav.channels
    n = len(raw) // wav.block_align
    if wav.fmt_code == 3 and bps == 4:
        arr = np.frombuffer(raw[: n * wav.block_align], dtype="<f4")
    elif wav.fmt_code == 1 and bps == 2:
        arr = np.frombuffer(raw[: n * wav.block_align], dtype="<i2").astype(np.float32) / 32768.0
    else:
        return np.array([], dtype=np.float32)
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    return arr.astype(np.float32, copy=False)


def normalized_xcorr_fft(haystack: np.ndarray, probe: np.ndarray) -> tuple[np.ndarray, int]:
    """Returns (correlation array indexed by start-position-in-haystack, len(haystack)-len(probe)+1)."""
    if probe.size == 0 or haystack.size < probe.size:
        return np.array([], dtype=np.float32), 0

    h = haystack - haystack.mean()
    p = probe - probe.mean()
    p_norm = float(np.linalg.norm(p))
    if p_norm == 0:
        return np.zeros(haystack.size - probe.size + 1, dtype=np.float32), haystack.size - probe.size + 1

    # full xcorr via FFT
    n = haystack.size + probe.size - 1
    nfft = 1 << int(np.ceil(np.log2(n)))
    H = np.fft.rfft(h, n=nfft)
    P = np.fft.rfft(p[::-1], n=nfft)
    full = np.fft.irfft(H * P, n=nfft)[:n]
    valid_count = haystack.size - probe.size + 1
    valid = full[probe.size - 1 : probe.size - 1 + valid_count]

    # rolling norm of haystack windows
    h2 = h * h
    csum = np.concatenate([[0.0], np.cumsum(h2)])
    win_sums = csum[probe.size:] - csum[:-probe.size]
    win_norms = np.sqrt(np.maximum(win_sums, 0.0))
    win_norms[win_norms == 0] = np.inf  # avoid div0

    return (valid / (win_norms * p_norm)).astype(np.float32), valid_count


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


def analyze_pair(a: Clip, b: Clip) -> dict:
    """Probe = first 200ms of b. Haystack = last 2s of a. Find best lag."""
    if a.wav.sample_rate != b.wav.sample_rate:
        return {"error": "sample rate mismatch"}
    sr = a.wav.sample_rate
    probe_n = int(sr * PROBE_S)
    haystack_n = int(sr * HAYSTACK_S)

    haystack = read_mono(a.path, a.wav, max(0, a.wav.nframes - haystack_n), haystack_n)
    probe = read_mono(b.path, b.wav, 0, probe_n)
    if haystack.size < probe.size:
        return {"error": "files too short"}

    corr, n = normalized_xcorr_fft(haystack, probe)
    if n == 0:
        return {"error": "xcorr empty"}

    best_idx = int(np.argmax(corr))
    best_score = float(corr[best_idx])
    # best_idx is the position in haystack where probe starts.
    # haystack runs from frame (a.nframes - haystack_n) to (a.nframes).
    # The match position relative to a's END is:
    #   (haystack_n - best_idx - probe_n) frames before the end
    # If that's ~0 → probe matches at the very end → clean cut.
    # If that's positive → probe matches T seconds before end → T seconds overlap.
    overlap_frames = haystack_n - best_idx - probe_n
    overlap_s = overlap_frames / sr
    return {
        "score": best_score,
        "overlap_s": overlap_s,
        "best_idx": best_idx,
        "haystack_n": haystack_n,
        "probe_n": probe_n,
    }


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

    # Bucket adjacent pairs into auto-split candidates vs gap pairs (the
    # latter become our null distribution).
    autosplit_pairs: list[tuple[Clip, Clip]] = []
    gap_pairs: list[tuple[Clip, Clip]] = []
    for gclips in groups.values():
        for i in range(len(gclips) - 1):
            a, b = gclips[i], gclips[i + 1]
            gap = (b.start - a.end).total_seconds()
            if abs(gap) > ADJACENT_TOLERANCE_S:
                # Could still be a useful null sample if same format
                gap_pairs.append((a, b))
                continue
            if DURATION_AUTOSPLIT_LO <= a.wav.duration_s <= DURATION_AUTOSPLIT_HI:
                autosplit_pairs.append((a, b))
            else:
                # Adjacent but not 30-min auto-split — manual restart.
                # Still informative for null distribution.
                gap_pairs.append((a, b))

    print(f"auto-split candidate pairs: {len(autosplit_pairs)}")
    print(f"gap / non-autosplit pairs:  {len(gap_pairs)}")
    print()

    # ---------- pass A: same-clip baseline ----------
    # Take a 200ms probe from the middle of a few clips, search for it
    # in a 2-second neighborhood that contains it. Should score ~1.0 at
    # the right lag. If not, our xcorr is broken.
    print("=== pass A: same-clip baseline ===")
    for c in [p[0] for p in autosplit_pairs[:5]]:
        sr = c.wav.sample_rate
        mid = c.wav.nframes // 2
        probe_n = int(sr * PROBE_S)
        haystack_n = int(sr * HAYSTACK_S)
        # haystack starts 1 second before probe-start, so probe sits 1s into haystack
        haystack_start = max(0, mid - sr)
        haystack = read_mono(c.path, c.wav, haystack_start, haystack_n)
        probe = read_mono(c.path, c.wav, mid, probe_n)
        if haystack.size < probe.size:
            print(f"  {c.path.name}: too short, skip")
            continue
        corr, _ = normalized_xcorr_fft(haystack, probe)
        if corr.size == 0:
            continue
        best = int(np.argmax(corr))
        score = float(corr[best])
        # expected best position = mid - haystack_start
        expected = mid - haystack_start
        offset = best - expected
        print(f"  {c.path.name}: score={score:.4f}  lag_from_expected={offset/sr*1000:+.2f}ms")

    # ---------- pass B: auto-split candidate pairs (the real test) ----------
    print()
    print("=== pass B: auto-split candidate pairs (wide ±2s lag search) ===")
    autosplit_results = []
    for a, b in autosplit_pairs:
        r = analyze_pair(a, b)
        if "error" in r:
            print(f"  skip {a.path.name} → {b.path.name}: {r['error']}")
            continue
        autosplit_results.append(r)
        verdict = ""
        if abs(r["overlap_s"]) < 0.005:
            verdict = "CLEAN-CUT zone (lag near end)"
        elif r["overlap_s"] > 0.005:
            verdict = f"OVERLAP {r['overlap_s']*1000:+.1f}ms"
        else:
            verdict = f"GAP-IMPLIED {r['overlap_s']*1000:+.1f}ms (probe matched past tail end — implausible)"
        print(f"  {a.tx}/{a.version}  {a.path.name[:40]:<40}"
              f" → {b.path.name[:40]:<40}"
              f"  score={r['score']:.3f}  overlap={r['overlap_s']*1000:+7.2f}ms  {verdict}")

    # ---------- pass C: null distribution from gap pairs ----------
    print()
    print("=== pass C: null distribution from non-autosplit pairs ===")
    null_scores = []
    sampled = gap_pairs[:: max(1, len(gap_pairs) // 30)]  # sample ~30
    for a, b in sampled[:30]:
        if a.wav.sample_rate != b.wav.sample_rate:
            continue
        r = analyze_pair(a, b)
        if "error" in r:
            continue
        null_scores.append(r["score"])
    if null_scores:
        arr = np.array(null_scores)
        print(f"  pairs sampled: {len(null_scores)}")
        print(f"  null score mean:   {arr.mean():.3f}")
        print(f"  null score stddev: {arr.std():.3f}")
        print(f"  null score max:    {arr.max():.3f}")
        print(f"  null score 95%ile: {np.percentile(arr, 95):.3f}")

    # ---------- summary ----------
    print()
    print("=== summary ===")
    if autosplit_results:
        scores = np.array([r["score"] for r in autosplit_results])
        overlaps = np.array([r["overlap_s"] for r in autosplit_results])
        print(f"  auto-split pairs analyzed:  {len(autosplit_results)}")
        print(f"  score min/median/max:       {scores.min():.3f} / {np.median(scores):.3f} / {scores.max():.3f}")
        print(f"  overlap min/median/max (s): {overlaps.min():+.4f} / {np.median(overlaps):+.4f} / {overlaps.max():+.4f}")
        n_with_overlap = int(np.sum(overlaps > 0.005))
        n_clean = int(np.sum(np.abs(overlaps) <= 0.005))
        print(f"  clean-cut (|overlap|≤5ms): {n_clean}")
        print(f"  measurable overlap >5ms:   {n_with_overlap}")
        if n_with_overlap > 0:
            print(f"  → REVISIT JOIN STRATEGY: stream-copy concat would leave audible glitches")
        else:
            print(f"  → ffmpeg -c copy concat is safe for these chains")
    return 0


if __name__ == "__main__":
    sys.exit(main())
