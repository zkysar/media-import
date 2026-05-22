# media-import

CLI for importing media off DJI Mic 2 transmitters, Sony A7C cards, and DJI Mavic Air 2 drones. See README.md for user-facing docs.

## Output layout

Files land at:

```
<dest>/RAW/<date>/<DEVICE-CLASS>/[<TX>/]<CATEGORY>/
<dest>/FLIGHTLOGS/<date>/                       # sibling to RAW/, per-card-session artifacts
```

- **RAW** — fixed top-level marker for raw, untouched offload. Reserves room for siblings like `EDIT/`, `EXPORT/`, or `FLIGHTLOGS/` (already used).
- **date** — `YYYY-MM-DD`, the recording date parsed from the filename (DJI mic) or EXIF (Sony, drone). Always present, even for single-date imports (consistent paths trump shorter ones).
- **DEVICE-CLASS** — `DJI-MICS` (mics), `SONY-A7C` (camera), or `DJI-DRONES` (Mavic Air 2). Always plural.
- **TX** — `TX01` / `TX02`, **DJI mic only**. The two transmitters genuinely need separate folders. Sony and drone have no per-body level: body-serial-per-folder was tried originally, but MP4 atoms carry no serial, the `UNKNOWN/` fallback folder was worse than no level, and one body per setup is the assumption. `MediaGroup.body_serial` is still populated for verify/diagnostic display, just not used in paths.
- **CATEGORY** — `EDIT`, `ORIG`, `TRANSCRIPTS` (DJI mic), or `PHOTOS`, `VIDEOS` (Sony, drone). Output kind for that device.

Folders are upper-case where possible; filenames are left as the camera/transmitter wrote them.

Example (DJI mic): `~/Audio/podcast/RAW/2026-05-03/DJI-MICS/TX01/EDIT/TX01_20260503_112250_140603_edit_joined.wav`

Example (Sony): `~/Photos/2026-05/RAW/2026-05-03/SONY-A7C/PHOTOS/DSC01234.ARW`

Example (drone): `~/Drone/2026-05/RAW/2026-05-07/DJI-DRONES/VIDEOS/DJI_0014.MP4` (with `.THM` and `.SCR` sidecars next to it). Flight log lands at `~/Drone/2026-05/FLIGHTLOGS/2026-05-07/dji.gis`.

`FLIGHTLOGS/` is a sibling to `RAW/` because per-card-session artifacts can't be tied to a single capture's date/device. Forcing them under `RAW/<date>/<DEVICE-CLASS>/` would invent a false mapping; siblinghood keeps the model honest.

## Devices

The script holds a `Device` dataclass with hooks (`detect`, `discover`, `filter_by_args`, `build_plan`, `completion_dates`) plus a `supports_transcribe: bool` flag. Three instances exist: `DJI_MIC`, `SONY_A7C`, `DJI_AIR_2`.

`ALL_DEVICES` is the ordered registry consulted by `select_device`. To add a fourth device: implement the hooks, build a `Device` instance, append it to `ALL_DEVICES`. `select_device`, `--device` parsing, and `cmd_complete` derive their behavior from the registry.

`select_devices` (the list form) returns every device detected when `--device auto`, in `ALL_DEVICES` order; an explicit `--device` returns just that one. `main()` imports them all in a single run: per-device read-only discovery, one shared dest prompt, one combined preview (each device's body block + a single aggregated time/disk-space footer), one Proceed gate, then each device's plan executed in sequence. Single-device is the N=1 case of the same path. A device that is non-viable (unverified Sony, or zero items after filtering) is dropped with a stderr note rather than aborting the others; the run only errors when nothing is left to import. `select_device` (singular) remains as a thin wrapper for completion dispatch.

`--device` accepts model-specific names (`dji-mic-2`, `sony-a7c`, `dji-air-2`) plus `auto`. Legacy aliases `dji` and `sony` are mapped at parse time with a stderr deprecation warning via `_DEVICE_ALIASES` / `_parse_device`. `select_device` only ever sees canonical names.

`Device.supports_transcribe` controls whether `--transcribe` is meaningful. Drone is False (audio is wind/motor); mic and Sony are True. The CLI rejects `--transcribe` at dispatch for unsupporting devices — no per-device branching inside `build_plan`.

`MediaGroup` is the per-capture record shared by Sony and drone (and any future per-clip-with-sidecars device). DJI mic stays on `Clip` + `Chain` because chain detection is mic-specific. Drone uses a `kind="flightlog"` MediaGroup for `MISC/GIS/dji.gis`; `dji_air_build_plan` routes that off the `RAW/` tree into `FLIGHTLOGS/`.

DJI mic has a special-cased step in `main()` between `discover` and `build_plan`: it calls `build_chains(discovered_files)` to detect 30-min auto-split boundaries and join them. This is not a Device hook because it's DJI-specific bookkeeping. If a fourth device needs similar per-device orchestration, that's the signal to refactor this step into the Device interface.

Sony imports are gated behind a one-time `--verify-sony` handshake. This command validates the scan output against a real card and writes `~/.cache/media-import/sony-verified.json`. Until that succeeds, `--device sony-a7c` (or auto-detect picking Sony) fails with a pointer to the verify command. Rationale: Sony code was implemented from specification ahead of access to real hardware; the gate prevents incompletely-validated code from running a real import. Drone has no such gate — the implementation was end-to-end validated against a copy of a real card before merge, so the constraint Sony was working around doesn't apply.

## Overwrite policy

`CopyOp.overwrite_existing` is the architectural source of truth for "this op is going to clobber an existing file." `classify_dst(final, expected_size)` is the helper every per-device `build_plan` calls:

- dst exists with matching size → returns `None`; caller skips the op entirely (idempotent re-run)
- dst doesn't exist → returns `(False, 0)`; normal new-file copy
- dst exists with a *different* size → returns `(True, existing_size)`; op is added with `overwrite_existing=True` so the preview can list it and `run_singleton_moves` knows to use `os.replace`

`Plan.overwrites` exposes flagged ops; `format_preview` lists them above the output-layout block so the user sees the warning next to the confirm prompt. Surprise size mismatches (different size, no flag — shouldn't happen if `build_plan` is correct) raise from `run_singleton_moves` before any moves complete.

## Conventions

- Plans for this repo live at `~/projects/plans/`, not in-tree (per global CLAUDE.md).
- `media-import` is a single Python file by design. No package split unless functionality genuinely warrants it. The `Device` dataclass + `ALL_DEVICES` registry keep per-device logic colocated, not strewn across modules.
- Stdlib only — no pip dependencies for the script itself. `openai-whisper` is the one optional runtime dep, gated behind `--transcribe` (used for DJI mic joined WAVs and Sony's video-extracted WAVs; rejected for drone). `ffmpeg` is used for DJI mic chain joining and Sony's audio extraction from video.
