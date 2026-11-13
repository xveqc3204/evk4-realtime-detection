# EVK4 Real-Time Detection

<!-- EBS_CROSS_PLATFORM_GUI -->
## Recording GUI on macOS and Windows

The **EVK4 detector and recording pipeline are unchanged**. Open the experiment control GUI without a camera connected.

- **macOS:** double-click `~/Applications/EBS Field Tests.app` after running `bash "Install EBS Desktop App.command"`, or use `bash "Start EBS Tests.command"`. Stop using **STOP & SAVE**.
- **Windows 11 x64:** double-click **`Start EBS Tests.bat`**. Set up Python 3.10 with tkinter and the pinned camera requirements first. To finish early, click the EVK4 dashboard and press **Q**, then let the GUI finalize the take. The Windows control window does **not** send a potentially destructive OS terminate signal.

See [platform setup](docs/PLATFORM_SETUP.md) for initial Windows camera-driver checks and the test procedure. Camera discovery and recording on Windows must be validated on the actual EVK4 and computer before comparing with Mac runs.
<!-- END EBS_CROSS_PLATFORM_GUI -->


Live event-based activity cueing with a Prophesee EVK4. The current GUI and
experiments are in **`rotor_lab/`**. The original terminal prototypes are
preserved in **`legacy/`**. Run the current application from this repository,
not from an older Downloads copy.

The purpose is to cue observation from raw activity first and add periodic
and possible-drone evidence when available. This is an experimental sensor,
not a validated drone classifier. No range, depth, or angular bearing is inferred.

## One working folder

Use the existing `~/evk4-realtime-detection` checkout for ongoing edits.
The Desktop shortcut **AE27 EBS - Working Repository** opens that same folder.
The separate `ece487-labs-xveqc3204` repository is coursework.

| Location | Use | Storage |
|---|---|---|
| `rotor_lab/` | Current application source | GitHub |
| `docs/` | Technical testing instructions | GitHub |
| `rotor_lab/captures/` | Default location for new recordings | Local, ignored by Git |
| `local-project/AE27 EBS - Cloud Folder/` | Reviewed runs, screenshots, project documents and review log | Local working files; upload to Drive |
| `legacy/` | Preserved earlier prototypes | GitHub |

The cloud folder is local to this Mac and is not included in a Git clone.
Its **Read Me First.docx** explains the review/upload routine. **Run Review Log.xlsx**
holds the review decisions and screenshot sources. The existing Desktop cloud-folder
shortcut points to this same location; it is not another copy.

Keep full recordings, signed forms, budgets and project administration in the
local cloud folder. This repository is public. GitHub is for source code and
technical documentation; it is not the backup for the full data collection.

## Start

Close any other EVK4 program. From the repository root:

```bash
cd ~/evk4-realtime-detection
bash run.sh test
bash run.sh check
bash run.sh
```

The launcher reuses a compatible existing Python environment and does not
install or upgrade packages. The camera check is a short acquisition/recording
check; a PASS does not establish drone detection. Unit tests and synthetic
inputs do not establish physical-camera or aircraft performance.

If automatic environment discovery fails, point to the Python executable
in your working camera environment. For example, only when this path exists:

```bash
export EVK4_PYTHON="$HOME/Downloads/evk4_distance_test/.venv/bin/python"
bash run.sh check
```

For a NEW installation only, while online:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The previously recorded Mac setup used Python 3.10.18, NumPy 2.2.6, Numba
0.61.2, OpenCV 4.12.0.88, neuromorphic_drivers 0.17.0, and Matplotlib 3.10.8.
The pinned application requirements remain unchanged. Do not upgrade a working
environment immediately before collection.

## Commands

All commands below are run from the repository root.

| Task | Command |
|---|---|
| Run software tests | `bash run.sh test` |
| Check camera and recording | `bash run.sh check` |
| Open live GUI | `bash run.sh` |
| Synthetic GUI demo | `bash run.sh demo` |
| Generic 60 s event and video recording | `bash run.sh capture --name bench` |
| Record with an extra native photo every 5 s | `bash run.sh capture --name bench --photos-every 5` |
| 25 mm lens at measured 20 m, 60 s distance trial | `bash run.sh 25 20 --focus-m 20 --aspect front` |
| Override a distance trial to 90 s | `bash run.sh 25 20 --duration 90 --aspect front` |
| Verify the latest distance trial | `bash run.sh verify latest` |
| Review the latest distance trial | `bash run.sh review latest` |
| Replay the latest distance trial | `bash run.sh replay latest` |
| Compare raw presets on the same latest events | `bash run.sh compare latest` |
| Build cross-run CSV and plots | `bash run.sh summary` |
| Save one native photo set after 5 s | `bash run.sh photo --after 5 --name snapshot` |

`latest` means the last **distance trial**, not the last generic capture,
preflight, or replay. For another recording, pass its absolute run-folder or
`events.evs` path. The launcher runs the app inside `rotor_lab/`, so relative
paths to data are resolved there. Use absolute paths outside that folder.

Generic `capture` forwards the original app record options, including
`--duration`, `--photos-every`, `--rgb`, `--notes`, `--run-dir`, `--no-events`,
and `--activity-preset`. A generic capture is not automatically scored as a
distance experiment. `capture --help` shows the app options.

## One minute means acquisition time

Generic record mode and distance trials default to **60 seconds**. Use
`--duration 30`, `--duration 60`, or `--duration 90` to choose another positive
live-capture duration. A scored distance trial requires at least 20 seconds.

The timer starts after live-source setup. Compilation, camera initialization,
shutdown, file verification, review, and graph generation can make the command
last longer. Movies start at the first fresh preview and use a nominal frame
rate. Their playback length is not guaranteed to equal 60 seconds if frames
are skipped. Use `video_frames.csv` and event timestamps for analysis.

Live monitoring without recording has no time limit. Replay reads its complete
source file. Photo mode uses `--after`, not `--duration`. The camera preflight
remains a short diagnostic, normally 5 seconds.

## What the three flags mean

- **ACTIVITY:** fresh persistent neighboring raw-event pixels, with A-number boxes.
  This does not require a rotor signature.
- **ROTOR EVIDENCE:** fresh confirmed localized periodic evidence, with P-number
  boxes and white supported pixels. It is not guaranteed prop-only segmentation.
- **DRONE CANDIDATE:** an explainable but unvalidated rule using associated raw
  activity and periodicity plus motion or multiple periodic regions.

No rotor evidence must not suppress ACTIVITY. An UNKNOWN identity is compatible
with a useful ACTIVITY cue. Missing/stale/invalid input is UNAVAILABLE, not a
confident negative. Coasting alone is not fresh positive evidence.

The yellow/blue view is recent event polarity. The white view is periodicity
selected within the 80-1200 Hz band, not a brightness threshold. The histogram
counts supported pixels, not FFT amplitude or confidence. Paths are image-plane
patch histories, not physical position or a count of drones.

Details: [ACTIVITY_FIRST.md](rotor_lab/ACTIVITY_FIRST.md).

## Recording and results

All new data lives under **`rotor_lab/captures/`**. Existing Downloads recordings
are not moved or deleted. A distance trial records both views in the same run.

```text
rotor_lab/captures/<unique_run>/
    events.evs              Original decoded events, not EVT3 RAW
    dashboard.mp4           Combined GUI preview
    raw_events.mp4          Clean yellow/blue preview
    filtered_events.mp4     Clean white/black preview
    video_frames.csv        Video frame timestamps and validity
    photos/                 Native snapshots and numerical evidence
    session.json            Actual settings, versions, and source identity
    telemetry.jsonl         Decisions, measurements, thresholds, and health
    cues.jsonl              Image-coordinate tracks and three flags
    summary.json            Input loss and processing/recording diagnostics
    trial.json              Lens/range/aspect metadata for distance trials
    review.json             Operator observations for distance trials
    code_used/              Source captured with the distance trial
```

Videos can fall back to AVI. At 5 million events/s, 60 s of decoded 13-byte
records is approximately 3.9 GB before videos. Monitor storage and verify
recordings before leaving the site. A clean file is not a correct detection.

`summary` creates `rotor_lab/captures/results/`. Only verified, reviewed live
distance trials appear in its figures. Raw/filtered visibility and cue-on-target
association require review. Whole-view rates/counts are not segmented target
measurements. A single run per condition is not detection probability.

## Controlled testing

Follow [docs/TESTING.md](docs/TESTING.md). Keep the camera fixed and thresholds
unchanged during a sweep. Record one target-present/absent marker pair per trial.
Compare settings on identical recorded events before selecting a new default.

## After a recording

1. Verify the finished run. Use the review command for distance trials; inspect
   the videos and logs for other captures. `latest` refers to a distance trial;
   use an absolute folder path for other runs.
2. Copy the complete run from `rotor_lab/captures/` into the cloud folder's
   `02 Run Data/To Review/<date>/`. Keep the original capture in place so existing
   latest-run pointers continue to work.
3. Record the review decision in **Run Review Log.xlsx** and sort the working copy
   into Keep, Unsure or Reject. Replay and synthetic inputs stay clearly labeled.
4. Upload the new run and any new screenshots to the matching Drive folders.
   Update the existing cloud copy of the log using Drive's **Upload new version**.

Git commits do not upload these recordings or update Drive. Keep each run's event
files, videos, settings, review records and logs together. Keep means retained for
analysis; it does not certify a successful drone detection.

## Updating the repository

Edit the files in this checkout instead of exporting another application copy
from Downloads. Before starting, check the working tree. When it is clean, bring
in remote changes with a fast-forward-only pull:

```bash
cd ~/evk4-realtime-detection
git status --short --branch
git pull --ff-only
```

If there are unfinished edits, finish or commit them before pulling. After editing,
run `bash run.sh test` for application changes and inspect `git diff`. Stage only
the files intended for the public repository. For example, for a README-only edit:

```bash
git add README.md
git diff --cached
git commit -m "Update project documentation"
git push origin main
```

For a code change, stage the specific source files instead. If the staged diff
is empty, skip the commit; push only existing local commits if needed. Use
meaningful commit messages. Do not force-push or use `git add .` for a data-collection session.
`local-project`, captures, environments and recorded media are ignored. Ignore
rules do not remove a file already tracked by Git. The old GUI export manifest is
historical provenance, not a list of files to export for each update.
