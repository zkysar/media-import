# media-import

CLI for importing media off DJI Mic 2 transmitters, Sony A7C cards, and DJI
Mavic Air 2 drones. Filters by date range, joins 30-minute auto-split mic
chains into single files (with per-pair byte-exact overlap trimming),
optionally transcribes via local Whisper. Shows a preview and time estimate
before doing anything, and flags any files that would be overwritten.

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
media-import --device sony-a7c --dest ~/Photos/2026-05
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
<dest>/RAW/<YYYY-MM-DD>/SONY-A7C/{PHOTOS,VIDEOS}/
```

Stills and video land in separate folders. No body-serial level — A7C MP4 atoms carry
no serial tag and the best-effort fallback created `UNKNOWN/` folders that were worse
than no level. One A7C body per setup is assumed.

**Sidecars:** `.ARW` alongside `.JPG` is copied verbatim — no transcoding, no skipping.
For video, `.MP4` plus its `M01.XML` sidecar are copied; the `T01.JPG` thumbnail in
`PRIVATE/M4ROOT/THMBNL/` is intentionally skipped.

**HEIF support:** `.HIF` files are intentionally unsupported (complexity vs. use-case
tradeoff).

**Date filtering:** `--from`, `--to`, `--days` filter by EXIF `DateTimeOriginal` (stills)
or `CreateDate` (video).

**Transcription:** `media-import --device sony-a7c --transcribe --dest <path>` transcribes video clips.
For each video, ffmpeg extracts the audio track to a 16kHz mono PCM WAV, then whisper
transcribes it. Both the extracted WAV and the `.srt` transcript land in `TRANSCRIPTS/`.
Photos are not transcribed — `--transcribe` only affects video groups. The intermediate
WAV stays on disk in `TRANSCRIPTS/<clipname>.wav` alongside the `.srt`; it is useful
for re-runs and audits.

## DJI Mavic Air 2

To import from a DJI Mavic Air 2 SD card:

```sh
media-import --device dji-air-2 --dest ~/Drone/2026-05
```

Or rely on auto-detection.

**Output layout:**

```
<dest>/RAW/<YYYY-MM-DD>/DJI-DRONES/{PHOTOS,VIDEOS}/
<dest>/FLIGHTLOGS/<YYYY-MM-DD>/dji.gis
```

No body-serial level — same reasoning as Sony (MP4s carry no serial, the
fallback `UNKNOWN/` folder was worse than no level). One drone per setup is
assumed.

**Sidecars:** `.THM` (160×90) and `.SCR` (960×540) JPEG previews from
`MISC/THM/<NNN>/` are copied alongside each video.

**Flight log:** `MISC/GIS/dji.gis` is per-card-session (not per-clip), so it
sits in a sibling `FLIGHTLOGS/` tree, not under `RAW/`. Date-bucketed by file
mtime.

**No `--transcribe`:** drone audio is wind and motor — never useful speech.
The flag is rejected for `--device dji-air-2` at dispatch time.

**Known quirk:** MP4 timestamps come from QuickTime `CreateDate` (UTC). Clips
shot near a UTC day boundary may bucket into the "wrong" local date.

## Multiple devices at once

If you plug in more than one device type (e.g. a Sony A7C card and a DJI Mic
transmitter), `auto` detects and imports them all in a single run. Everything
lands under one `--dest`, separated by device class (`RAW/<date>/SONY-A7C/`,
`RAW/<date>/DJI-MICS/`, ...). You get one preview and one confirmation covering
all of them.

## Overwrite handling

For all devices, the preview lists any files that would replace existing
content (same path, different size). Same-size existing files are skipped
silently — re-running with the same args is safe and idempotent. A surprise
size mismatch with no overwrite intent (shouldn't happen if `build_plan` is
correct) raises before any moves so partial state can't accumulate.

## Flags

| Flag                  | Default      | Notes |
|-----------------------|--------------|-------|
| `--dest <path>`       | (required)   | Where files land. See [Output layout](#output-layout). With a trailing slug, treated as the parent root. |
| `<slug>` (positional) |              | Trailing positional. When given, the proposed dest is `<dest>/<earliest-shoot-date>-<slug>/`, where the date is read from the media's EXIF/filename after discovery. After scanning, you're prompted `Dest [<proposed-path>]:` — press enter to accept, type an absolute path to override. `--yes` skips the prompt. Slug must be lowercase alnum with single dashes (e.g. `media-import --days 1 --dest /Volumes/zachssd poster`). |
| `--device <name>`     | `auto`       | One of `auto`, `dji-mic-2`, `sony-a7c`, `dji-air-2`. Legacy aliases `dji` and `sony` still work but warn. |
| `--from YYYY-MM-DD`   | earliest     | Filter by recording timestamp from filename (DJI mic) or EXIF (Sony, drone). |
| `--to YYYY-MM-DD`     | today        | Inclusive. |
| `--days N`            |              | Shorthand for `--from <N days ago>`; mutually exclusive with `--from`/`--to`. |
| `--version edit\|orig\|both` | `both` | Which version(s) of each clip to import. (DJI mic only) |
| `--mic TX01\|TX02\|all` | `all`      | Filter by transmitter. (DJI mic only) |
| `--join` / `--no-join` | `--join`    | Join 30-min auto-split chains. (DJI mic only) |
| `--transcribe`        | off          | Transcribe joined/singleton files (DJI mic) or video clips (Sony). Rejected for `dji-air-2`. |
| `--model <name>`      | `tiny`       | Whisper model. Use tab completion to see what's cached. |
| `--verify-sony`       | off          | One-time verification of Sony import code; required before first real import. |
| `--yes`               | off          | Skip confirmation prompt. |
| `--dry-run`           | off          | Preview only. |
| `--eject`             | off          | After a successful import, try to eject each source volume via `diskutil eject` (best-effort; failures are reported but not fatal). |

## Tab completion

Once installed, tab completion provides:

- `--from <TAB>` / `--to <TAB>` — recording dates currently on connected mics, with clip counts
- `--mic <TAB>` — `TX01`, `TX02`, `all`
- `--version <TAB>` — `edit`, `orig`, `both`
- `--model <TAB>` — only the whisper models actually present in `~/.cache/whisper/`
- `--dest <TAB>` — directory completion

## Output layout

```
<dest>/RAW/<YYYY-MM-DD>/<DEVICE-CLASS>/[<TX>/]<CATEGORY>/
```

- `RAW/` — top-level marker for raw offload. Always present.
- `<YYYY-MM-DD>` — recording date from the filename (DJI mic) or EXIF (Sony, drone). Always present.
- `<DEVICE-CLASS>` — `DJI-MICS`, `SONY-A7C`, or `DJI-DRONES`.
- `<TX>` — `TX01` / `TX02`, **DJI mic only**. The two transmitters genuinely need
  separate folders, so the level is required there. Sony and drone don't have an
  equivalent level: body-serial-per-folder was tried, but MP4s carry no serial and
  the `UNKNOWN/` fallback folder was worse than no level at all. One body per setup
  is assumed.
- `<CATEGORY>` — `EDIT`, `ORIG`, `TRANSCRIPTS` (mic), or `PHOTOS`, `VIDEOS` (Sony, drone).

`FLIGHTLOGS/<YYYY-MM-DD>/` is a sibling to `RAW/` for per-card-session
artifacts (currently just DJI's `dji.gis` flight telemetry).

Example (DJI mic): `~/Audio/podcast/RAW/2026-05-03/DJI-MICS/TX01/EDIT/TX01_20260503_112250_140603_edit_joined.wav`

Example (Sony): `~/Photos/2026-05/RAW/2026-05-03/SONY-A7C/PHOTOS/DSC01234.ARW`

Example (drone): `~/Drone/2026-05/RAW/2026-05-07/DJI-DRONES/VIDEOS/DJI_0014.MP4`

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
search on `prev.tail == cur.head`) and trims accordingly before concat.

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
