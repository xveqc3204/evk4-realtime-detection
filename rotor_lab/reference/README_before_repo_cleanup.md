# Activity-first patch installed

For current commands, three-flag meanings, presets and recording/replay, read
[ACTIVITY_FIRST.md](ACTIVITY_FIRST.md). Test scope is in [PATCH_TESTS.md](PATCH_TESTS.md).
The material below is the historical September 15 baseline documentation. Its
single-cue description predates the independent raw-activity addition.

# September 15 baseline: paired distance tests

This is the supplied Rotor Lab v0.3 application with a small experiment wrapper.
It restores the September 15-style dashboard. It is NOT a new detector or a terminal-only rollback.
The exact program and settings installed on September 15 are not known until that run's files are supplied.

## What stayed the same

`rotor.py`, `ui.py`, `settings.json`, `event_io.py`, `media.py`, `report.py`, and `requirements.txt` are byte-identical to the supplied v0.3 ZIP. The hash manifest verifies this.

The GUI still has yellow/blue raw events, white supported periodic pixels, patch boxes and IDs, a frequency histogram, image-plane paths, photos, and videos. `ROTOR_CANDIDATE` still requires fresh confirmed periodic support. White pixels alone do not assert the flag.

The 80-1200 Hz band, four consistent periods per polarity, 20% period tolerance, six supporting pixels, 60 ms confirmation, 33 ms raw display history, and 40 ms host-processing limit are unchanged.

There is no new test box, motion hold, automatic retuning, activity fallback pretending to be rotor evidence, or drone-identification claim.

## The only application change

The expensive live filter allocation/compilation and host-information lookup happen before USB acquisition opens. This carries forward the initialization-order correction without changing the estimator or ignoring losses. Extra startup diagnostic records are saved. See `reference/STARTUP_ONLY.diff`.

All experiment measurement and cross-run work is in `field.py`, outside the live detector.

## Open

Extract this folder into Downloads. Keep your existing folders and recordings.

```bash
cd ~/Downloads/evk4_sep15_baseline
bash test.sh check
bash test.sh
```

`test.sh` reuses an existing camera environment without updating its packages. It checks this folder, the original v0.3 folder, the distance-test folder, and v0.5. It never edits those folders.

If no environment is found, install once while online:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

`check` receives and records actual camera data without a GUI. A PASS means file/acquisition checks passed, not that the target will pass the filter. The second command opens the familiar live GUI. Close every other program using the EVK4.

Optional synthetic GUI test:

```bash
bash test.sh demo
```

This uses explicitly labeled synthetic data. It is not aircraft validation.

## One real recording per lens and distance

```bash
bash test.sh 25 10
```

First number: lens focal length in mm. Second number: measured camera-to-target range in m.
Each trial lasts 30 seconds and saves original decoded events, dashboard/raw/filtered videos, and native photos every 5 seconds. It uses the FULL FIELD. It does not gate the cue to an added box.

Proposed test stations for every available lens (25 mm first, then 16 and 50 mm): 10, 15, 20, 25, 30 m. These are suggested marked stations, not predicted or safe flight ranges. Use only the approved available space and enter the actual distance. Same distances for every lens make comparisons interpretable.

Set focus once per lens at 20 m, then leave it fixed throughout that lens's sweep. If your chosen focus is different, record it explicitly with `--focus-m`. Match aperture where possible; record lighting and aperture rather than inventing values. The software does not focus the lens.

```bash
bash test.sh 25 15
bash test.sh 25 20
bash test.sh 25 25
bash test.sh 25 30
```

For a different focus or additional metadata:

```bash
bash test.sh 25 10 --focus-m 15 --f-number 2.8 --lux 500
```

The last two numbers above are examples only. Use measured values or omit the options.

## During each run

Keep the camera fixed. Use your approved site and operator. Keep the known target OUT of the camera view for at least six seconds after live imagery begins. Press **1** once when it reaches the marked test position. Observe it for about ten seconds. Press **2** once when it leaves the view. Let recording finish. Press **S** for an extra photo; **Q** stops early. Do not change ROI, reset evidence, or change settings during a formal trial.

The program checks recording integrity and then asks four short y/n/u questions: valid presentation, raw target visible, filtered target visible, and confirmed cue ON the target. Use `u` if unsure. The final cue judgment is checked against the live log, but software cannot establish target association for you.

The five seconds before marker 1 are the paired baseline. Markers refer to the last displayed sensor timestamp and are approximate operator annotations, not synchronized ground truth. Wrong, missing, or repeated markers leave a trial unresolved instead of producing an invented score.

## Results

- **PERIODIC_CUE_ON_KNOWN_TARGET:** a fresh cue was logged in the presentation interval and the operator observed it on the known target. This is not autonomous drone identity.
- **ACTIVITY_ONLY:** target visible in raw or filtered events without a verified target-associated cue.
- **NO_TARGET_EVIDENCE:** valid known target presentation, reviewed as not seen in either view and no cue on target.
- **UNREVIEWED / REVIEW_CONFLICT / INCOMPLETE_RUN / INVALID_PRESENTATION:** retained separately, never silently converted to misses.

Raw and filtered visibility are separate reviewed observations. The raw stream has no new automatic classifier in this build.

```bash
bash test.sh summary
open captures/results
```

Outputs: `results.csv`, `results.json`, and separate PNG/SVG figures for each lens/focus/aperture/lux/settings group. All runs stay in the CSV. Only reviewed, verified live runs appear in figures. One point is one run, not a fitted probability estimate.

The plots show reviewed raw/filtered visibility and cue result versus distance, whole-view raw event rate versus distance, and whole-view median supported pixels versus distance. Counts are NOT segmented drone measurements. Baseline and target-present values are separate. Raw rate and periodic-pixel count have different definitions and their ratio is not filter retention.

A no-target room trial or separate reference video is useful for checking background interference. Do not tune parameters until a frozen baseline has been reviewed.

## Inspect a run later

```bash
bash test.sh review latest
bash test.sh replay /full/path/to/run/events.evs
```

Replay reruns this archived v0.3 filter using the included settings, not necessarily undocumented settings from another build. It writes a new replay folder. Replay is not a live throughput test. Use the original `session.json` to compare parameters before interpreting differences.

Each formal run includes `code_used/`, the exact source bytes and settings at launch, source hashes, and structured `trial.json`. Source data is never deleted. Keep original events and `video_frames.csv` even after making presentation clips. Videos are downsampled 20 Hz previews; they are not the original event stream or a precise latency instrument.

At 5 million events/s, 30 seconds of decoded events uses about 1.95 GB plus media. Rate varies. Check free space before the whole sweep.

## Data needed from September 15 and the later failure

For the run named in the screenshot, send `session.json`, `telemetry.jsonl`, `summary.json`, and a native photo's `pixel_data.npz` if available. A 5-10 second original-event excerpt around the visible target is ideal. The original code used that day, especially `rotor.py`, `app.py`, `ui.py`, and settings, establishes any local changes. Do not substitute code from today's folder and call it historic.

A small evidence ZIP can be made without touching the recordings:

```bash
bash test.sh bundle /full/path/to/your/run
```

This bundles small logs and up to the first two native photo sets, not multi-GB videos or events. The tool prints the output path in Downloads. Review contents before sharing. Provide the same small files from one failed run for comparison.

The screenshot visibly contains supported pixels while the flag is zero. That demonstrates that those are different stages; it does not show why confirmation was missing. We will not weaken the flag just to make it positive.

## Verification boundary

See `VERIFICATION.md`. Software regression and synthetic recordings were exercised in this environment. The exact September 15 run, physical EVK4, Mac window interaction, and real aircraft have not been tested here. This package preserves the known archived architecture; it does not promise that a physical failure has been diagnosed without the real data.
