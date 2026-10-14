# Project status

## Current application

The activity-first GUI is versioned in `rotor_lab/`. Use `bash run.sh` from the
repository root. The root no longer advertises the old terminal-only scripts
as the current product; those are preserved under `legacy/`.

This cleanup was prepared against upstream main commit
`fa4a50565b1ac3f8fea6031addf8359d234d7d06`. The inspected rotor_lab tree matched
GitHub tree `68df23b14f0a56859680dd82cf55d79a4e91d17c` byte-for-byte.

## Changes in this cleanup

- Root launcher and current README; old terminal files archived intact.
- Generic record and paired distance-trial defaults changed from 30 to 60 s.
- Existing `--duration` still overrides the default for live capture.
- Simple capture/photo aliases, verify command, and latest-trial replay/compare.
- Existing environment reuse extended to repo-root and working baseline folders.
- No automatic dependency upgrades through the root launcher.
- One-minute test checklist and command-reference documentation.

## Deliberately unchanged

Raw/periodic detection, candidate rules, presets, frequency band, thresholds,
GUI drawing, tracking, camera-driver configuration, event format, media encoder,
queue bounds, loss handling, and processing limits. Old results remain intact.
This is a usability/organization change, not improved detection performance.

## Evidence and limits

The previously supplied September 15 live run contained substantial periodic
pixels and positive cue transitions, as well as four processing overruns and
observed input loss. It lacked target-presence markers and setup details needed
for target-associated detection metrics. It does not validate the new raw branch.

The new activity-first algorithm remains a software-tested prototype. Physical
EVK4, actual aircraft, Mac UI/codec, target association, and performance at range
require local checks. Synthetic runs validate software paths, not real-world
recall, false-cue rate, low-light advantage, range, or total system power.

Next: a target-free recording, raw-only localized motion, and a controlled
front-facing hover sweep, followed by limited aspect and crossing comparisons.
See `docs/TESTING.md`. No autonomous sensor steering is implemented.
