# EVK4 GUI-only field recording

This is a **recording control interface around the existing `rotor_lab/app.py`**, not
an algorithm or camera-driver update. There are two windows: a small recording
control window and the familiar live EVK4 dashboard. **No Terminal input is
needed between experiments.**

## Open it

From Finder, double-click `Start EBS Tests.command` in the repository folder.
If macOS blocks a newly downloaded command file, review the file before approving
it. The command launches the installed Python with Tkinter; it installs nothing.
Keep the small launcher Terminal window open, but operate using the GUI.

If the GUI says "Camera Python environment not found", create or select the
existing compatible Python environment before going into the field. You can set
`EVK4_PYTHON` to the absolute path of the already-working interpreter. No
packages or camera drivers are automatically upgraded.

## One test, one folder

In the control window:

1. Select a local **Dataset folder** outside the Git repository. By default it
   is `~/Downloads/EBS_Field_Data_<date>`. Do not record directly into a
   cloud-synced folder because synchronization can produce extra I/O.
2. Enter **Indoor or Outdoor**, installed lens, measured range, declared focus,
   aperture/lux if actually known, light source, aspect, motion profile, and repeat.
3. Click **START RECORDING**. The existing EVK4 dashboard opens. Keep the target
   absent initially for raw background calibration.
4. Inside the dashboard press **1** at target entry, **2** at target exit,
   **S** for a native snapshot. These create the application's existing sensor-
   referenced markers. No Terminal input is involved.
5. Click **STOP & SAVE** in the control window, or let the 60-second default
   finish. The program uses its existing graceful shutdown and report writer.
   **Do not close the control window while it says FINALIZING**.
6. Review the status in the control window. `DATA_GAP`, `VIDEO_MISSING`, or
   `ERROR` must be investigated; they are not negative detections. Use **Open
   last run** to inspect the raw, filtered and dashboard videos.

Use duration `0` to record until you click Stop. Duration `60` uses the existing
60-second record mode. **The timer applies to acquisition, not compilation,
shutdown, or the nominal video playback length.**

## Resulting Google Drive folder

```
EBS_Field_Data_YYYY-MM-DD/
  Tests/
    YYYYMMDD_HHMMSS__INDOOR__L75__R20__front__hover__REP1__xxxxxx/
      events.evs                 decoded original events when available
      dashboard.mp4 / .avi       GUI preview when available
      raw_events.mp4 / .avi      unfiltered event preview
      filtered_events.mp4 / .avi periodic-supported view
      photos/                    native event snapshots and values
      session.json              original sensor and filter configuration
      telemetry.jsonl           decisions, events and processing health
      cues.jsonl                existing three-flag cueing logs
      markers.jsonl             keys 1/2/S and operator timing
      summary.json              camera processing and input loss
      media.json                recorded-media details
      report/                   original per-run graph exports
      trial.json                lighting, optics, distance, metadata, quality
      operator.log             original subprocess console log after finish
      reference/               optional manually attached conventional video
  Documents/                    add chosen reports using GUI
  INDEX.csv                     time-ordered run catalog and integrity
  README.txt
```

The application stores the complete original per-take output without modifying
its timestamps or event format. CSV includes **recording quality**, not measured
drone detection accuracy. Review target association separately using the video
and event records. Existing runs and the old archive are never edited.

You can choose **Attach reference video** after a run to copy a conventional-camera
movie into that same take. Reference videos are *not* synchronized by the tool.

You can choose **Add documents** in the GUI to copy a few intended Word,
PowerPoint, PDF or spreadsheet reports. Existing same-named documents are not
overwritten. After all runs, upload the dataset folder as a whole to Google
Drive. Do not delete local originals until the upload is verified.

## Controlled indoor/outdoor comparison

Hold the aircraft, lens, range, focus, f-number, target aspect, motion, camera
settings, and detector version fixed across paired experiments whenever
possible. Describe daylight vs indoor fixtures and measure lux with a documented
meter and orientation when feasible. A phone lux estimate is only an estimate.
Collect a target-absent background interval and several repeated target
presentations. Avoid tuning detector parameters between environments.

The unchanged software reports ACTIVITY, ROTOR EVIDENCE and DRONE CANDIDATE
independently. It does **not** conclusively identify aircraft. Periodic light
flicker can resemble rotor evidence. The default unchanged settings are the
80-1200 Hz periodicity acceptance band, four consistent periods per polarity,
20% tolerance, six supporting pixels, and 60 ms patch confirmation. The raw
activity branch is the existing sensitive preset. These are existing values,
not new optimizations.

## Verification and known boundaries

The new GUI wrapper is unit-tested using a local temporary dataset and mocked
process control. The unchanged application previously had its own software
regression suite. The external Stop action sends **SIGINT** to the existing
application main process, which has a graceful `finally` block. A stop pressed
while the camera/compiled worker is still initializing may leave an incomplete
run, and any driver, disk, codec or data-loss error must be investigated.

We have **not tested this GUI on your Mac or physical EVK4**. Before going to
field tests, do a short target-free acquisition, use Stop & Save, inspect the
video/event files, and check `trial.json` and `summary.json`. This is a soft
real-time research prototype; recorded host delay is not full detection latency.

<!-- EBS_CROSS_PLATFORM_DOC_LINK -->
## macOS and Windows

Both systems use the same detector and original-event format. The launchers and Windows stop control differ; for the verified procedure, see [platform setup](PLATFORM_SETUP.md).
<!-- END EBS_CROSS_PLATFORM_DOC_LINK -->
