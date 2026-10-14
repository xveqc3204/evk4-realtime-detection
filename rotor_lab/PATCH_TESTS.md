# Activity-first verification

## Completed in this environment

- 165 application/regression tests passed, including original detector/fault
  cases, raw-only detection, isolated noise rejection, weak-target presets,
  independent flags, unavailable state, native filter equivalence, optional
  period-input masking, cue withdrawals, metadata, GUI composition, and replay
  annotation checks. The baseline hash test now verifies the archived unchanged
  rotor/UI references, rather than claiming the intentional hook/UI edits have
  unchanged source hashes.
- Original default filter output was compared exactly against the archived
  rotor implementation on deterministic events. This checks unchanged rules,
  not real-world sensitivity.
- Full synthetic recording: 4,403,795 decoded events, zero reported input clears
  or recording error. All three movies decoded to 191 frames each, matching the
  video timestamp table. Native photo capture was exercised.
- The same original synthetic recording was replayed through both raw presets;
  comparison CSV and separate PNG/SVG flag timelines were created.
- A six-second simulated scene completed with 8,312,269 events and source end.
  Synthetic generation/processing on this shared host can be substantially slower
  than scene time. Earlier longer exploratory runs timed out. The synthetic-only
  timestamp cache removes repeated strided searches, but no real-time guarantee is
  inferred from this demo. Short deterministic worker tests are the primary
  regression checks. Original sensor/recording APIs are unchanged.

- The optional neighbor mode also replayed the same 4,403,795 events to source
  end, preserving raw activity and reporting its separately filtered periodic
  evidence. This is not a measured improvement on real recordings.
- 12 installer/export safety tests passed, including unknown-source refusal,
  backup, idempotence, undo, preserving recordings, and allowlisted Git export.
- A separately installed copy passed all 165 application tests.

- Final short movie/photo/report smoke test: 446,226 decoded events; three
  movies each decoded to 78 frames and matched the timestamp table; verification
  passed. Original event file and recording metadata remained usable.

## Environment actually used

Linux x86_64; Python 3.13.5; NumPy 2.3.5; Numba 0.65.1;
OpenCV Python 4.13.0.92; Matplotlib 3.10.8. The Mac environment in the supplied
session was NOT reproduced. Fetching a Python 3.10 test environment failed here.
No requirements or packages on the user's machine were upgraded.
Version-specific official API review is documented in API_NOTES.md.

## Not run / camera-dependent

- Physical EVK4, actual Mac GUI/input/codec, or actual aircraft.
- Real failed-range replay, real target recall or false-cue rates. Original real
  events.evs was not supplied, only logs. No claimed threshold optimum or range.
- Precision end-to-end latency, angular calibration, depth or external sensor cue.
- Continuous camera motion compensation. Camera movement can create activity and
  periodic look-alikes; neither flag establishes identity.

## Before field use

Run `bash test.sh test`, `bash test.sh check`, and a short recorded real-camera
trial. Inspect original events and video outputs. Keep failed recordings and loss
logs. A software PASS alone does not certify detection performance or losslessness.
