# media-import

CLI for importing media off DJI Mic 2 transmitters and Sony A7C cards. See README.md for user-facing docs.

## Output layout

Files land at:

```
<dest>/RAW/<date>/<DEVICE-CLASS>/<DEVICE>/<CATEGORY>/
```

- **RAW** — fixed top-level marker for raw, untouched offload. Reserves room for siblings like `EDIT/` or `EXPORT/` later.
- **date** — `YYYY-MM-DD`, the recording date parsed from the filename. Always present, even for single-date imports (consistent paths trump shorter ones).
- **DEVICE-CLASS** — `DJI-MICS` today. Reserved for `SONY-A7C` etc. when the tool generalizes (see `~/projects/plans/2026-05-04-dji-import-multi-device-research.md`). Always plural.
- **DEVICE** — `TX01`, `TX02` for mics. The specific physical device within the class.
- **CATEGORY** — `EDIT`, `ORIG`, or `TRANSCRIPTS`. Output kind for that device.

Folders are upper-case where possible; filenames are left as the camera/transmitter wrote them.

Example: `~/Audio/podcast/RAW/2026-05-03/DJI-MICS/TX01/EDIT/TX01_20260503_112250_140603_edit_joined.wav`

This shape replaces an earlier `<dest>/<category>/[<date>/]<device>/` layout. The new shape groups a day's shoot into one folder and leaves room for additional device classes without restructuring.

## Conventions

- Plans for this repo live at `~/projects/plans/`, not in-tree (per global CLAUDE.md).
- Empirical evidence for non-obvious behavior (e.g. TX01 vs TX02 overlap) goes in `verify_overlap_v*.py`. Keep these — they're the receipts behind decisions baked into the script.
- `media-import` is a single Python file by design. No package split unless functionality genuinely warrants it.
- Stdlib only — no pip dependencies for the script itself. `openai-whisper` is the one optional runtime dep, gated behind `--transcribe`.
