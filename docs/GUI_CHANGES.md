# GUI-only patch change record

New files only: `Start EBS Tests.command`, `rotor_lab/operator_gui.py`,
`rotor_lab/tests/test_operator_gui.py`, `docs/GUI_FIELD_TESTS.md`, and `docs/GUI_CHANGES.md`.

No modifications to existing `app.py`, `event_io.py`, `media.py`, `rotor.py`,
`activity.py`, `ui.py`, `field.py`, `settings.json`, `activity_presets.json`,
existing tests, or requirements. The source is checked against GitHub main
commit `04af3569361e718c9aed15412461f74f5c95023c` for the frozen
camera/filter/recording files before installation.

The control GUI launches the same `app.py record` with `--duration`,
`--run-dir`, `--config`, `--activity-preset`, and `--period-input`, keeps the
normal application dashboard, and sends SIGINT to the main process for
Stop & Save. Each run has its own original files and experiment metadata.
Nothing is pushed or uploaded automatically.
