# Flight-test checklist: independent activity and periodic evidence

Purpose: assess real-time activity cueing separately from possible-drone evidence.
Use the current GUI, original event recording and native pixel coordinates.

## Before collection

[ ] Camera check and a short verified recording succeed on the actual Mac.
[ ] Raw view responds. Activity-only test with a moving nonperiodic object raises
    ACTIVITY without requiring either other flag. An isolated pixel is rejected.
[ ] A target-free background is observed for at least 6 s. Check unintended lights,
    fans and reflections. Do not calibrate with the target in the scene.
[ ] Record lens, focus, aperture, actual range, lighting, view/aspect and settings.
[ ] No other application owns the EVK4. Enough storage is available.

## Minimum real collection

Keep camera fixed. Use only authorized positions and approved flight procedures.
Proposed common stations: 10, 15, 20, 25 and 30 m, where available. These are test
positions, not detection-range predictions or safety clearances. Start with the
available 25 mm lens, then 16/50 mm if available. Focus each lens at the same
reference mark (proposed 20 m), then keep that focus for its distance sweep.
This deliberately characterizes fixed-focus performance, including defocus.

[ ] Target-free clutter at each lens/setup before target trials.
[ ] Near-to-far front-facing hovers at marked distances, same target aspect/height.
[ ] At one reference distance: oblique and side hovers; then lateral crossing.
[ ] Target-free moving person/object, fan/light and periodic-background controls.
[ ] Separate camera-motion trial only after fixed-camera behavior is understood.
    Camera motion is not compensated; do not interpret it as new object motion.
[ ] Repeat reference and marginal-distance trials. Keep tuning flights separate
    from evaluation flights. With only one recording, label results exploratory.

For each trial use one recording for BOTH raw and filtered measurements. Press 1
at target presence, 2 at absence, and S for a native snapshot. Verify saved files.
Operator keys are approximate labels, not synchronized precision-latency truth.
Record target-associated boxes when possible; do not count background cues as hits.

## Controlled replay and acceptance

[ ] Re-run original events with the same rotor settings and initial context.
[ ] Compare conservative raw baseline versus sensitive raw support group only.
[ ] Retain a separate same-data trial for neighbor input; do not change both groups
    and attribute the difference to one parameter. Native periodic mode is default.
[ ] Inspect ACTIVITY misses and target-absent cue episodes. Then inspect rotor and
    possible-drone flags, including how often these add useful target evidence.
[ ] Check native box overlap/accuracy, fresh-track coverage, ID switches, timing,
    flag transitions, UNKNOWN reason counts and unavailable intervals.
[ ] Inspect processing p50/p95/max and source loss independently. Driver delay is
    not end-to-end detection latency. Replay is not a physical timing benchmark.

Keep changes only when held-out target-associated activity improves without
exceeding a PREDECLARED false-cue and delay allowance, without new data loss, and
without breaking near-target recording/replay. Enter limits before evaluating:
False cue episodes/min allowed: ____  Host p95 budget: ____  Miss tolerance: ____
No-data periods are not successful negatives. Moving lights can pass the candidate
rule. More flags, fewer UNKNOWN labels or a whiter image alone are not success.

If no rotor-resolving events exist, record ACTIVITY with insufficient rotor
 evidence. Do not lower identity requirements to manufacture a drone detection.
Synthetic tests check implementation. They do not establish real-world detection.
