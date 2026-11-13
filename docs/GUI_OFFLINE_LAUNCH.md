# EBS GUI offline startup and Mac shortcut

The existing `rotor_lab/operator_gui.py` controller can now open **without an EVK4 connected**. Nothing in `rotor_lab/app.py`, `rotor.py`, `activity.py`, `event_io.py`, `media.py`, `ui.py`, or settings is changed.

The top line distinguishes `USB detected`, `USB not detected`, and `status unavailable`. It uses macOS `system_profiler SPUSBDataType` to report *USB enumeration only*, not proven driver access or a healthy stream. The camera check runs on an idle background thread every ~8 seconds or on demand, and **does not poll while a recording process is running**. Dependencies are also checked asynchronously. The offline `Preview settings` button validates metadata without recording.

One-time installer, from a checked-out copy of the actual repo:

```bash
python3 ~/Downloads/EBS_GUI_Offline_Launch_Fix/apply.py --target ~/evk4-realtime-detection
cd ~/evk4-realtime-detection
bash "Start EBS Tests.command"
```

To create a clickable macOS app in `~/Applications`:

```bash
bash "Install EBS Desktop App.command"
open "$HOME/Applications/EBS Field Tests.app"
```

From then on, double-click the app from `~/Applications`, or drag it to the Dock. The app references the **existing repository**; do not move that repository after installation. This is a locally generated, unsigned AppleScript applet, not a packaged Python executable. It needs a user-installed Python 3.10+ with Tkinter. It does not install/update Python or any dependencies. If it fails to open, check `~/Library/Logs/EBSFieldTests/launcher.log` or run `bash "Start EBS Tests.command"` to see the exact error. If Gatekeeper asks, use Finder's normal per-app approval process for software you trust. Do not disable Gatekeeper globally.

The GUI opens without a camera. To actually record, connect the EVK4 using a USB 3 cable, wait for `USB detected`, and verify the camera window receives events. This GUI status is not a substitute for preflight or recording integrity checks.

After a run, do not interrupt the finalization step. Each test writes into `EBS_Field_Data_<date>/Tests/<timestamp>.../` with original `events.evs`, dashboard/raw/filtered videos (where available), logs, photos, metadata and reports. Quality labels remain available in `INDEX.csv`. Record to local storage, not a Google Drive-synced directory during acquisition.

For new tests, keep frequency thresholds and activity settings fixed between indoor/outdoor comparisons. Record optics, illumination, geometry and target presentation accurately. An unverified periodic cue is not established drone identity.

<!-- EBS_CROSS_PLATFORM_DOC_LINK -->
## macOS and Windows

Both systems use the same detector and original-event format. The launchers and Windows stop control differ; for the verified procedure, see [platform setup](PLATFORM_SETUP.md).
<!-- END EBS_CROSS_PLATFORM_DOC_LINK -->
