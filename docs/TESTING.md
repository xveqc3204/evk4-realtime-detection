# One-minute test checklist

Run these commands from `~/evk4-realtime-detection`. Keep the current camera
and detector configuration. Do not change the frequency band, ROI, filter mode,
and raw preset all at once. Native periodic input and sensitive raw activity
are the initial test settings. These are experimental, not validated optima.

## 1. Open the correct code and check it

```bash
cd ~/evk4-realtime-detection
git status --short --branch
bash run.sh test
bash run.sh check
df -h .
```

Close other EVK4 applications before the camera check. Pass requirements:
software tests succeed, camera opens, events arrive, no reported input loss or
recording error. A zero rotor flag during a hand-motion camera check is normal.
The default preflight is 5 s; `bash run.sh check --seconds 15` extends it.
It is not a formal one-minute target experiment.

Open the GUI:

```bash
bash run.sh
```

Hold the camera fixed, let it observe target-free background, then move a
contrasting card in front of it. Look for an A-number track and ACTIVITY=1,
even when ROTOR EVIDENCE and DRONE CANDIDATE remain zero. The filtered view
need not retain nonperiodic motion. After motion ends, fresh activity should
clear. Press Q before starting another camera command.

If this basic cue fails, preserve a short recording and logs. Do not spend the
entire night collecting a distance series before this path is verified.

## 2. Record the room without a target: 60 s

```bash
NEG="$PWD/rotor_lab/captures/background_$(date +%Y%m%d_%H%M%S)"
bash run.sh capture --duration 60 --photos-every 5 --run-dir "$NEG" \
  --activity-preset sensitive --period-input native \
  --notes "Target absent throughout. Fixed camera. Add lens, aperture and illumination."
bash run.sh verify "$NEG"
open "$NEG"
```

No target-presence keys are needed in a generic target-free control. Review
unexpected A/P boxes and cue episodes. A fan/light may be a valid periodic
measurement but a source-identification false cue. This capture has no
`trial.json` or scored distance review; it remains available for replay/compare.
It is intentionally excluded from the distance-summary figures.

## 3. Record localized nonperiodic motion: 60 s

```bash
RAW="$PWD/rotor_lab/captures/raw_motion_$(date +%Y%m%d_%H%M%S)"
bash run.sh capture --duration 60 --run-dir "$RAW" \
  --notes "No aircraft. Fixed camera. Nonperiodic card movement after target-free background."
bash run.sh verify "$RAW"
```

Use about 0-10 s without motion, 10-45 s with localized movement, then rest.
ACTIVITY should not depend on a periodic patch. Watch that its box belongs to
the moving object and clears afterward. Do not require DRONE CANDIDATE=1.
This generic negative control is not scored as a known-drone presentation.

## 4. Reference target trial: 60 s

Use an approved area and qualified operator. Do not fly toward personnel or
handle an armed aircraft. Front describes aircraft orientation, not a command
to approach the camera. Keep the camera fixed tonight.

For an ACTUAL 25 mm lens, measured 20 m range, and lens physically focused at 20 m:

```bash
bash run.sh 25 20 --duration 60 --focus-m 20 --aspect front --profile hover
```

The numbers are examples only where those lenses, marked distances, and
clearances exist. The software records range/focus declarations; it measures
neither range nor physical focus. Use the actual available values.

Use ONE target interval per distance trial:

| Approximate elapsed capture time | Operator action |
|---|---|
| 0-10 s | Target absent. At least 6 s must elapse after fresh imagery starts. |
| Around 10 s | Press 1 once when target is presented in view. |
| About 10-45 s | Consistent hover/presentation. S saves an extra native photo. |
| Around 45 s | Press 2 once when target leaves the view. |
| Remainder to 60 s | Target absent. Let the application finish. |

Do not change ROI or reset evidence during a formal run. If you must, mark it
as interrupted. B/N setting changes are locked during event/video recording.

The duration is acquisition time after source setup, not a promise of an exact
movie playback duration. Q stops early. The command may continue during saving,
verification, review, and graph generation after the capture stops.

After capture, the wrapper verifies files and asks y/n/u review questions:
valid presentation, raw target seen, filtered pixels on target, and periodic cue
on target. The cue question refers to ROTOR EVIDENCE, not drone identity.
Use unsure instead of guessing. Unknown, invalid, and incomplete are not misses.

Independent ACTIVITY/ROTOR_EVIDENCE/DRONE_CANDIDATE outputs and detailed reasons
are in cues.jsonl/telemetry.jsonl and results.csv. A flag anywhere during a
presentation is not automatically associated with the target. Inspect boxes.

## 5. Distance sweep with one focus setting per lens

Proposed marks: 10, 15, 20, 25, 30 m. Use actual approved indoor stations;
these are not predicted detection limits or safe-distance prescriptions.
Start with 25 mm. If time is short, use 10, 20, and 30 m first. The reference
trial above already supplies 20 m. Run each trial separately:

```bash
bash run.sh 25 10 --focus-m 20 --aspect front
bash run.sh 25 15 --focus-m 20 --aspect front
bash run.sh 25 25 --focus-m 20 --aspect front
bash run.sh 25 30 --focus-m 20 --aspect front
```

Each command defaults to 60 s. Set the physical focus once per lens at the same
reference position, leave it fixed during the sweep, and record the aperture.
Keep lighting, target height, aspect, and presentation behavior consistent.
The aim is fixed-focus system performance, not best focus at every range.

Repeat at the same distances for available 16 mm and 50 mm lenses. Example
reference commands:

```bash
bash run.sh 16 20 --focus-m 20 --aspect front
bash run.sh 50 20 --focus-m 20 --aspect front
```

A repeated condition gets a new folder. Label repeats explicitly:

```bash
bash run.sh 25 20 --focus-m 20 --aspect front --repeat 2
```

Optional `--f-number`, `--lux`, `--target`, and `--notes` record actual metadata.
Do not invent unmeasured values. A one-minute run remains one trial, not 60
independent repetitions. Add repeats near the observed success/failure boundary.

## 6. Small aspect/motion check at the reference station

```bash
bash run.sh 25 20 --focus-m 20 --aspect oblique --profile hover
bash run.sh 25 20 --focus-m 20 --aspect side --profile hover
bash run.sh 25 20 --focus-m 20 --aspect side --profile crossing
```

All default to 60 s. Suggested oblique/side orientations are about 45/90 degrees,
but record the actual setup. Crossing means target motion, not camera motion.
Keep one marked interval and inspect box association, continuity, and clearing.
Do not expect a single front-facing result to establish all-aspect detection.

## 7. Verify, replay, and compare without another flight

```bash
bash run.sh verify latest
bash run.sh replay latest
bash run.sh compare latest
```

`latest` selects the last lens/distance trial, not the most recent generic run.
For the explicit background control captured above:

```bash
bash run.sh compare "$NEG/events.evs"
```

Paired comparison uses identical original events and source-session rotor
settings, varying the raw preset. Interactive replay uses the current settings.
It does not recreate lost events, hardware latency, or historical ROI changes.
The comparison writes a NEW timestamped output folder printed in Terminal.

After baseline-vs-sensitive is understood, test the only optional period-input
alternative on the same recording:

```bash
bash run.sh compare latest --period-input neighbor
```

Compare matching presets across native/neighbor results. Do not conflate this
change with raw-sensitivity tuning. Neighbor support can remove weak real signal.
Without annotations, the reports are descriptive episodes/coverage, not accuracy.
Annotations with time intervals and target boxes enable the implemented
association and overlap metrics; see ../rotor_lab/ACTIVITY_FIRST.md.

## 8. Compile results and decide what to keep

```bash
bash run.sh summary
open rotor_lab/captures/results
```

Only verified, reviewed live distance trials enter the summary figures. All
trials remain in CSV. Generic controls need their own replay/telemetry review.
Raw/filtered target visibility is operator-reviewed. Event rate and filtered
pixel counts are whole-view unless the run used a specified ROI. They have
different definitions; their ratio is not a filter retention percentage.

Keep changes only when target-associated activity improves within a predeclared
false-cue and processing-delay allowance, without data-loss or near-target
regression. Preserve evaluation recordings separately from those used to tune.
Do not choose settings merely because UNKNOWN is rarer or more pixels are white.

Before leaving, open the actual videos/native photos, run file verification,
check source_clears/processing_overruns/recording errors, and copy data to backup
storage. Do not delete recordings merely because a summary CSV exists. At
5 Mev/s, each minute of decoded events is about 3.9 GB before video; seven such
runs need about 27.3 GB plus video. Real event rate varies substantially.
