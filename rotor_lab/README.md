# Rotor Lab: active application

Run from the repository root: `bash run.sh`.

- [Repository setup and commands](../README.md)
- [One-minute test checklist](../docs/TESTING.md)
- [Three flags, algorithms, presets, and evidence limits](ACTIVITY_FIRST.md)
- [Existing algorithm tests and boundaries](PATCH_TESTS.md)

The active pipeline is `event_io.py -> app.py -> activity.py + rotor.py -> ui.py`.
The `field.py` wrapper manages distance-trial metadata, review, and results.
`compare_activity.py` replays identical events with two raw presets.

Recordings and reports stay under `rotor_lab/captures/`, which is ignored by Git.
`test.sh` is the existing launcher and works directly from this folder, too.
The older `run.sh` inside this folder is a bootstrap utility that can install
packages. Prefer the repository-root `run.sh`, which delegates to `test.sh`
and never installs packages automatically.

`reference/` and `BASELINE_MANIFEST.json` preserve the earlier filter and GUI
for provenance/equivalence tests. `EXPORT_FILES.txt` records the earlier
code-only import. Do not use the old exporter or its file list to overwrite
or stage future changes; inspect and stage the specific files you edited.

The default raw preset is `sensitive`. The periodic-input mode is `native`.
The three flags are independent outputs, not mutually exclusive identities.
A possible-drone heuristic remains unvalidated on real field data.

Repository cleanup changes only entry points, documentation, and recording
session defaults. It does not change activity/period detection, tracking,
GUI drawing, acquisition, queues, data-loss guards, media encoding, or replay
signal processing. Generic record mode and distance trials default to 60 s.
`--duration` overrides live-capture duration. Live monitoring is unlimited;
replay processes the original file to EOF.
