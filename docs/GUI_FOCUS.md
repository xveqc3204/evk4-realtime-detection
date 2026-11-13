# Focus first, then record

## Open and focus

Open the existing EBS Field Tests.app on a Mac, or Start EBS Tests.bat on Windows.
The controls open offline. Actual raw preview and recording need the EVK4 connected.
Wait for Recording software: READY and refresh the camera connection when needed.

Click **Focus camera (no recording)**. A separate window shows native-resolution
raw ON events in yellow and OFF events in blue, using a 33 ms display history.
This is an event visualization, not a normal intensity photograph.

Manually turn the lens focus ring. Gently move a high-contrast card at the intended
focus distance if the scene is static and produces few visible events. This is not
autofocus. No periodicity filter, detector, tracking or scientific metrics run in
this preview. No take folder, movies, events.evs, photos, metadata or index is saved.
There is no focus recording to clean up.

Click **Finish focusing**, press Q/Esc in the focus window, or close that window.
Wait for the window to close and START RECORDING to become available. Focusing and
recording cannot use the camera at the same time. Idle camera probes are paused
while previewing. If the preview fails, the controller shows a diagnostic; no take
is manufactured. Standard launcher/OS diagnostics are separate from test data.

## Record

1. Keep the default NEW local daily dataset folder, or choose a new local/external
   folder. Do not select the old archive, an old export, or a cloud-synced directory.
2. Enter Indoor/Outdoor, physical lens, measured range, focus, aspect, repeat and
   duration. Keep 60 seconds for the one-minute trials. Leave unknown lux/aperture blank.
3. Click START RECORDING. This still runs the unchanged app.py with its existing
   recording arguments and settings. Keep the target absent for the first 6-10 seconds.
4. Select the camera dashboard and press 1 when the target enters and 2 when it
   leaves. S takes an extra snapshot. The controller and dashboard are two windows.
5. Let the timer end, or use STOP & SAVE on Mac. On Windows use Q in the dashboard
   for an early safe stop. Leave the controller open until FINISHED.
6. Open last run. Check original events and movies and review any DATA_GAP, missing
   video or ERROR status. RECORDED_UNREVIEWED is not proof of correct detection.
7. Update metadata and repeat. Add documents and attach reference video only after
   recording. Attach reference video belongs to the most recent take and is not synced.

## Upload

Open dataset. Upload the complete new EBS_Field_Data_<date> folder to the existing
Google Drive project as a new daily dataset. No organizer/exporter step is needed.
It contains Tests/<timestamped take>/, Documents/, INDEX.csv and README.txt.
The original event format, movies, timestamps and logs are unchanged. The index
contains current test metadata and recording quality, not the historical Keep/Unsure
review catalog. Do not overwrite the historical index or move individual movie files
away from their event data. Keep originals until the backup is checked.

## Exact scope

Only operator_gui.py is edited. New files: focus_preview.py, this guide and
 tests/test_focus_preview.py. app.py, activity.py, rotor.py, event_io.py, media.py,
ui.py, settings.json, activity_presets.json and requirements.txt are unchanged.
Focus uses the installed neuromorphic_drivers with the same default configuration
and iterator settings as the existing LiveSource. NumPy maximum.at keeps the latest
ON/OFF timestamps per pixel, including repeated pixel coordinates. No Numba compile
or recording module is used by preview. It is a disposable focusing aid, not a
measurement instrument. It may clear delayed preview buffers to keep the view current.

Verified API references: NumPy 2.2 ufunc.at;
https://numpy.org/doc/2.2/reference/generated/numpy.ufunc.at.html
OpenCV 4.12 HighGUI;
https://docs.opencv.org/4.12.0/d7/dfc/group__highgui.html
Existing project event_io.LiveSource with neuromorphic_drivers 0.17.0.

No detector thresholds, sensor biases, dependency versions or scientific outputs are
changed by this patch. Physical Mac/Windows camera operation still requires a local check.
