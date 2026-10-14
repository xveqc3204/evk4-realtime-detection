# Checks performed on this package

Basis: the supplied archived Rotor Lab v0.3 ZIP, not recovered bytes from the user's September 15 installation.

- 113 automated software tests passed: 79 inherited v0.3 tests, 25 wrapper/result tests, and 9 startup-order tests.
- Source hashes confirm the filter, GUI, settings, event I/O, media implementation, report implementation, and pinned requirements were not altered.
- The sole change inside the application is the live initialization-order fix and startup diagnostics. No grace period or raised loss threshold was added.
- A synthetic full-app recording wrote and verified 2,271,534 events, raised and cleared its periodic cue, and saved native photos.
- The dashboard, raw, and filtered videos each decoded to 378 frames, matching the timestamp table.
- The GUI was visually inspected from a native synthetic snapshot. No interactive Mac window was tested.
- Wrapper classification rules, missing/duplicate annotations, modified recordings, and synthetic-run exclusion were tested.
- A labeled artificial-results fixture exercised the PNG/SVG plot exports. It is not field evidence and is not included in captures.
- The one-page DOCX was rendered and inspected.

Synthetic processing ran slower than sensor time during portions of the shared-host integration test. Its 10-second synthetic stream produced a longer wall-clock movie. This validates file plumbing, not live throughput or latency. Synthetic/replay paths do not apply every live deadline check.

No actual EVK4, physical drone, September 15 event recording, or macOS desktop interaction was available here. Software test success does not establish real target sensitivity, drone identity, detection range, or data completeness at the sensor.

See validation/regression.log, integration_verification.json, integration_summary.json, and environment.json. Run bash test.sh check locally and retain both successful and failed data.
