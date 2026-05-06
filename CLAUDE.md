# media-import

CLI for importing media off DJI Mic 2 transmitters and Sony A7C cards. See README.md for user-facing docs.

## Output layout

Files land at:

```
<dest>/RAW/<date>/<DEVICE-CLASS>/<DEVICE>/<CATEGORY>/
```

- **RAW** — fixed top-level marker for raw, untouched offload. Reserves room for siblings like `EDIT/` or `EXPORT/` later.
- **date** — `YYYY-MM-DD`, the recording date parsed from the filename (DJI) or EXIF (Sony). Always present, even for single-date imports (consistent paths trump shorter ones).
- **DEVICE-CLASS** — `DJI-MICS` (mics) or `SONY-A7C` (camera). Always plural.
- **DEVICE** — `TX01`, `TX02` for mics; body serial for Sony. The specific physical device within the class.
- **CATEGORY** — `EDIT`, `ORIG`, `TRANSCRIPTS` (DJI), or `PHOTOS`, `VIDEOS` (Sony). Output kind for that device.

Folders are upper-case where possible; filenames are left as the camera/transmitter wrote them.

Example (DJI): `~/Audio/podcast/RAW/2026-05-03/DJI-MICS/TX01/EDIT/TX01_20260503_112250_140603_edit_joined.wav`

Example (Sony): `~/Photos/2026-05/RAW/2026-05-03/SONY-A7C/0123456789/PHOTOS/DSC01234.ARW`

This shape replaces an earlier `<dest>/<category>/[<date>/]<device>/` layout. The new shape groups a day's shoot into one folder and accommodates multiple device classes without restructuring.

## Devices

The script holds a `Device` dataclass with hooks: `detect(volumes)`, `discover(volume)`, `filter_by_args(files, args)`, `build_plan(files, args)`, and `completion_dates(volume)`. Two instances exist: `DJI_MIC` and `SONY_A7C`.

`select_device(volumes, requested)` routes the `--device` argument to the right instance. `--device auto` inspects all mounted volumes and picks the appropriate device based on filesystem signatures.

DJI has a special-cased step in `main()` between `discover` and `build_plan`: it calls `build_chains(discovered_files)` to detect 30-min auto-split boundaries and join them. This is not a Device hook because it's DJI-specific bookkeeping. If a third device needs similar per-device orchestration, that's the signal to refactor these steps into the Device interface.

Sony imports are gated behind a one-time `--verify-sony` handshake. This command validates the scan output against a real card and writes `~/.cache/media-import/sony-verified.json`. Until that succeeds, `--device sony` (or auto-detect picking Sony) fails with a pointer to the verify command. Rationale: Sony code is implemented from specification ahead of access to real hardware; the gate prevents incompletely-validated code from running a real import.

## Conventions

- Plans for this repo live at `~/projects/plans/`, not in-tree (per global CLAUDE.md).
- Empirical evidence for non-obvious behavior (e.g. TX01 vs TX02 overlap) goes in `verify_overlap_v*.py`. Keep these — they're the receipts behind decisions baked into the script.
- `media-import` is a single Python file by design. No package split unless functionality genuinely warrants it. The `Device` dataclass + module-level instances keep this honest — Sony's per-device logic lives next to DJI's, not in a separate module.
- Stdlib only — no pip dependencies for the script itself. `openai-whisper` is the one optional runtime dep, gated behind `--transcribe`.
