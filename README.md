# media-import

CLI for importing audio off DJI Mic 2 transmitters. Filters by date range,
joins 30-minute auto-split chains into single files (with per-pair byte-exact
overlap trimming), optionally transcribes via local Whisper. Shows a preview
and time estimate before doing anything.

## Quickstart

Plug in both DJI mics, then:

```sh
media-import --dest ~/Audio/podcast-2026-05 --transcribe
```

The script will:

1. Scan all mounted volumes for DJI files
2. Parse filenames + WAV headers to find clips
3. Detect auto-split chains (per spec §3 detection rule)
4. Print a preview with time estimate
5. Wait for `y` to proceed
6. Copy → join (with overlap trimming) → move singletons → transcribe → cleanup

See `~/projects/plans/2026-05-04-media-import-design.md` for the full design.

## Sony A7C

To import from a Sony A7C card:

```sh
media-import --device sony --dest ~/Photos/2026-05
```

Or rely on auto-detection (works when only one card is mounted):

```sh
media-import --dest ~/Photos/2026-05
```

**First-time setup:** Before importing from a real Sony card for the first time, run:

```sh
media-import --verify-sony
```

This validates the scan output against the card's actual structure and writes a marker to
`~/.cache/media-import/sony-verified.json`. Subsequent imports skip this step. (Background: Sony
code is specified ahead of access to a real card, so the gate prevents incomplete code from
corrupting an import.)

**Output layout:**

```
<dest>/RAW/<YYYY-MM-DD>/SONY-A7C/<body-serial>/{PHOTOS,VIDEOS}/
```

The body serial comes from EXIF `SerialNumber`. If EXIF is unavailable, falls back to
`UNKNOWN`. Stills and video land in separate folders.

**Sidecars:** `.ARW` alongside `.JPG`, and `.XML`/`.THM` alongside `.MP4` are copied
verbatim — no transcoding, no skipping.

**HEIF support:** `.HIF` files are intentionally unsupported (complexity vs. use-case
tradeoff).

**Date filtering:** `--from`, `--to`, `--days` filter by EXIF `DateTimeOriginal` (stills)
or `CreateDate` (video).

**Transcription:** Sony video transcription lands in a future commit (P3.x). `--transcribe`
is currently a no-op for Sony video.

## Flags

| Flag                  | Default      | Notes |
|-----------------------|--------------|-------|
| `--dest <path>`       | (required)   | Where files land. See [Output layout](#output-layout). |
| `--device auto\|dji\|sony` | `auto`  | Choose device. `auto` picks DJI or Sony based on what's mounted. |
| `--from YYYY-MM-DD`   | earliest     | Filter by recording timestamp from filename (DJI) or EXIF (Sony). |
| `--to YYYY-MM-DD`     | today        | Inclusive. |
| `--days N`            |              | Shorthand for `--from <N days ago>`; mutually exclusive with `--from`/`--to`. |
| `--version edit\|orig\|both` | `both` | Which version(s) of each clip to import. (DJI only) |
| `--mic TX01\|TX02\|all` | `all`      | Filter by transmitter. (DJI only) |
| `--join` / `--no-join` | `--join`    | Join 30-min auto-split chains. (DJI only) |
| `--transcribe`        | off          | Transcribe joined files + singletons (skips individual chain members). DJI only for now. |
| `--model <name>`      | `tiny`       | Whisper model. Use tab completion to see what's cached. |
| `--verify-sony`       | off          | One-time verification of Sony import code; required before first real import. |
| `--yes`               | off          | Skip confirmation prompt. |
| `--dry-run`           | off          | Preview only. |

## Tab completion

Once installed, tab completion provides:

- `--from <TAB>` / `--to <TAB>` — recording dates currently on connected mics, with clip counts
- `--mic <TAB>` — `TX01`, `TX02`, `all`
- `--version <TAB>` — `edit`, `orig`, `both`
- `--model <TAB>` — only the whisper models actually present in `~/.cache/whisper/`
- `--dest <TAB>` — directory completion

## Output layout

```
<dest>/RAW/<YYYY-MM-DD>/<DEVICE-CLASS>/<DEVICE>/<CATEGORY>/
```

- `RAW/` — top-level marker for raw offload. Always present.
- `<YYYY-MM-DD>` — recording date from the filename (DJI) or EXIF (Sony). Always present.
- `<DEVICE-CLASS>` — `DJI-MICS` or `SONY-A7C`.
- `<DEVICE>` — `TX01` / `TX02` (DJI), or body serial (Sony).
- `<CATEGORY>` — `EDIT`, `ORIG`, `TRANSCRIPTS` (DJI), or `PHOTOS`, `VIDEOS` (Sony).

Example (DJI): `~/Audio/podcast/RAW/2026-05-03/DJI-MICS/TX01/EDIT/TX01_20260503_112250_140603_edit_joined.wav`

Example (Sony): `~/Photos/2026-05/RAW/2026-05-03/SONY-A7C/0123456789/PHOTOS/DSC01234.ARW`

## Auto-split detection

DJI Mic 2 auto-splits internal recordings at exactly 1800.045 seconds (30 min
+ 45 ms per file). This script detects chains by looking for files where:

1. The previous file's duration is in `[1799.5, 1800.5]` seconds
2. The next file's start timestamp is within ±2 seconds of the previous file's end

Files that meet both conditions are joined. Files that meet only the second
condition (manual pause/resume) are kept separate — silently splicing
unrelated takes would be wrong.

### Overlap

DJI behavior varies by transmitter:

- **TX02** writes sample-accurate clean cuts (0 frames of overlap).
- **TX01** writes ≥2 seconds of byte-identical overlap at every boundary.

The script does per-pair byte-exact overlap detection at runtime (binary
search on `prev.tail == cur.head`) and trims accordingly before concat. See
`verify_overlap_v3.py` for the empirical evidence.

## Install

### Via dotfiles (`dots`)

If you use the dotfiles flow at `~/projects/dotfiles/`, this repo is declared
as a `[[project]]` in the manifest. After cloning dotfiles on a new machine:

```sh
cd ~/projects/dotfiles
bin/bootstrap   # installs deps + clones declared projects
bin/link        # creates symlinks
exec zsh
```

### Stand-alone

If you want it without the dotfiles flow:

```sh
git clone <this-repo> ~/projects/utils/media-import
cd ~/projects/utils/media-import
make install
exec zsh
```

`make install` symlinks:
- `~/.local/bin/media-import` → `media-import`
- `~/.zsh/completions/_media-import` → `completions/_media-import`

`make uninstall` removes both.

## Tests

```sh
make test
```

Tests cover WAV-header parsing (32-bit float DJI files + 16-bit PCM fallback)
and chain-detection rules. Synthetic WAV fixtures are generated by
`tests/fixtures/make_fixtures.py` (run before first test if the fixtures dir
is empty).

## Runtime requirements

All already standard on a developer Mac:

- Python 3.11+ (stdlib only — no pip dependencies)
- `ffmpeg` on PATH (for trim and concat)
- `exiftool` on PATH (for Sony A7C metadata reads; install with `brew install exiftool`)
- `openai-whisper` Python package (only if using `--transcribe`)
- macOS volume mounting at `/Volumes/*`

## Idempotency

A re-run with the same args:

- Skips singleton copies whose dest size equals source size
- Skips joined files whose dest exists with matching frame count
- Skips transcripts whose `.txt` already exists
- Resumes cleanly after Ctrl-C (staging is left intact)

If a join produces a corrupt output (frame-count mismatch), the script
deletes the partial file before raising — so the next run can retry.
