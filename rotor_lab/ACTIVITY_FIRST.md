# Activity-first patch: run instructions

This patch targets the supplied `evk4_sep15_baseline` application. It does not
replace the project directory, install packages, edit recordings, or push to Git.
The installer refuses unknown local changes. The previous periodic filter is
retained in native mode; the raw activity branch is new and separately reported.

## Start

Close other EVK4 programs. From the existing application folder:

```bash
bash test.sh test
bash test.sh check
bash test.sh
```

`test.sh` reuses the existing Python environment without upgrading it. The first
launch compiles code before opening USB. A synthetic demo is optional:

```bash
bash test.sh demo
```

The raster-based quad demo can take time to build and may run below real time on
some hosts. It is a software exercise, not a physical-camera throughput result.

## Three flags, one familiar window

- ACTIVITY: fresh persistent raw-event cluster. A yellow/blue raw view and A-number
  boxes show the support. Frequency rejection cannot disable this branch.
- ROTOR EVIDENCE: fresh confirmed localized periodicity using the original rules.
  The white filtered view and P-number boxes show the supporting pixels. This is
  rotor-like optical evidence, not proof of rotating propellers.
- DRONE CANDIDATE: an experimental possible-drone rule requiring associated raw
  activity and periodicity, a raw track spanning at least 200 ms, and either at
  least 8 pixels of image displacement or two periodic regions separated by at
  least 8 pixels inside the raw track's padded box. Moving lights/fans can pass.
  A stationary unresolved rotor can remain UNKNOWN. This is not a validated
  source classifier, rotor count, confidence score, or confirmed identity.

These are not mutually exclusive. ACTIVITY=1, ROTOR EVIDENCE=0,
DRONE CANDIDATE=0 is an intentional usable activity cue with unknown identity.
No current valid input means UNAVAILABLE, represented by null flags in logs,
not a confident absence. UNKNOWN reasons are insufficient_activity,
insufficient_rotor_evidence (including failed association/corroboration), or
unavailable_invalid_data. Detailed measurements and thresholds are retained.

The existing `rotor_candidate` field remains a compatibility alias for periodic
evidence, not for the new DRONE_CANDIDATE flag. Old per-run reports retain that
meaning. `field.py` also exports each new flag separately in results.csv.

## Sensitive raw preset and conservative reference

The default is `sensitive`. Change these three raw support/persistence values as
a related group, without altering rotor acceptance:

| Raw rule | baseline reference | sensitive test |
|---|---:|---:|
| Distinct neighboring pixels per component | 4 | 2 |
| Background-normalized cell threshold | 3 | 2 |
| Supporting observations in recent four | 3 | 2 |

These are starting test values, not values fitted to the failed real recording.
There was no independent raw detector in the September 15 GUI, so the `baseline`
name here means the conservative reference of the NEW raw branch. The original
application is preserved in the installer backup for the historical comparison.

Raw support uses a separate 20 ms sensor-time window, at native pixels, followed
by 8-pixel grouping cells. An isolated native pixel cannot support itself. It
needs an adjacent active native pixel. The first 1 s learns target-free
background; allow 6 s of target absence in formal recordings. Foreground cells
are excluded from adaptation. Stable unwanted adjacent sources can still cue.
Single-pixel distant targets are intentionally unresolved by this noise guard.

The original rotor settings remain 80-1200 Hz, 4 periods per polarity, 20%
tolerance, 6 supporting pixels, and 60 ms confirmation. The raw-view history
remains 33 ms and affects visualization, not the new raw support window.

```bash
bash test.sh live --activity-preset baseline
bash test.sh live --activity-preset sensitive
```

B toggles the raw preset when monitoring. N toggles native/neighbor period input.
Changes are logged and reset affected track/evidence state. Changes are locked
while recording events OR video. Original S/F/O/C/A/R/1/2/Q keys remain.
Use R and target absence for recalibration after changing the view or background.

## One optional alternative, off by default

```bash
bash test.sh live --period-input neighbor
```

This adds causal 8-neighbor support within 1 ms to the PERIODICITY input only.
It is an experiment for isolated noise disturbing period measurement. It can
remove weak/fast target signal too. Raw acquisition, raw activity timestamps,
raw display, and original event recording still see all received events.
The existing native mode is the default. Do not change preset AND this mode in
one comparison. This is not a new frequency band or motor-only segmentation.

## Record one paired distance trial

```bash
bash test.sh 25 10 --aspect front --activity-preset sensitive
```

This means an actual 25 mm lens, measured 10 m range, 30 seconds, original events,
raw/filtered/dashboard movies and native snapshots every 5 s. The declared focus
distance defaults to 20 m; the operator must physically set the lens. Override
with `--focus-m` when the actual setting differs. Optional `--duration`,
`--f-number`, `--lux`, `--profile hover|crossing`, `--repeat` and `--notes` remain.
Do not invent values; keep the lens focus fixed for its sweep.

Target absent for 6 s after live imagery begins. Press 1 at presentation, 2 on
exit. Keep the same aspect and approximate hover interval. Answer the original
short visibility/periodic-cue review afterward, using unsure rather than guessing.
The current frequency histogram counts pixels, not spectrum amplitude or belief.
Original event data is preserved at 13 bytes/event before overhead: 30 s at
5 million events/s is about 1.95 GB, before video.

Additional output: `cues.jsonl` contains sensor time in microseconds, host receipt
context, A/P track ID, native image box/center, validity, all three flags, evidence
and reasons. Source gaps and shutdown withdraw cues. This is a local log, not a
new external-sensor integration. No angle, range, depth, or physical velocity is
inferred. `telemetry.jsonl` records thresholds, raw measurements and UNKNOWN
reasons per evaluation. `session.json` records settings, versions and code hashes.

## Replay exactly the same events

```bash
bash test.sh replay /path/to/events.evs --activity-preset baseline
bash test.sh replay /path/to/events.evs --activity-preset sensitive
bash test.sh compare /path/to/events.evs
```

The compare command selects the original session's saved rotor configuration,
replays identical events with both raw presets, and writes a NEW timestamped
comparison directory with two logs, CSV summaries and PNG/SVG flag timelines.
Interactive replay preserves the existing behavior of using current settings;
use compare for source-session rotor settings and a controlled paired comparison.
No camera is needed for replay. Do not compare different flights as if only the
preset changed. Replay cannot recover events lost during capture. It does not
reproduce hardware latency or automatically apply historical manual ROI changes.
Use fixed configuration/ROI segments. Known original input loss is reported.

```bash
bash test.sh compare /path/to/events.evs --period-input neighbor
```

This is a separate experiment with the same raw presets and the optional filter.
Without annotations, reports are descriptive cue coverage/episodes, not accuracy.
Optional annotations are sorted nonoverlapping sensor-time intervals:

```json
[{"start_us":6000000,"end_us":16000000,"target_present":true,"bbox":[500,250,700,450]}]
```

The numbers above illustrate the schema only. Draw actual boxes and times from
reference data. Boxes are constant over each supplied interval, so use shorter
intervals for a moving target. Supply negative intervals explicitly.
`--annotations /path/annotations.json` adds target-associated coverage and
mean box IoU where boxes exist. An IoU of at least 0.1 is the declared diagnostic
association rule, not a claimed tracking standard. Presence-only intervals give
scene-cue coverage, not target recall. Original known-loss files withhold accuracy.
Repeated snapshots are time-weighted only up to 40 ms each; gaps are unobserved.

## Limits and test status

Read PATCH_TESTS.md and TEST_PLAN.md. The integrated code is software-tested on
Linux. It has NOT been tested with the physical EVK4, actual drone, or your Mac's
installed dependency versions in this environment. No real original events.evs
was supplied, so no real missed-detection, false-cue or range improvement is claimed.
Do not keep a sensitive preset merely because UNKNOWN appears less frequently.
