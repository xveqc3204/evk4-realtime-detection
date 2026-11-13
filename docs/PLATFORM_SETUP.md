# Running EBS Field Tests on macOS and Windows

**The application uses the same Python detector, EVK4 event-processing code, saved formats, and fixed experiment settings on both platforms.** The launchers and operating-system camera access differ. The Windows EVK4/GUI workflow requires testing on the actual Windows PC and camera before relying on it for field data. Do not change detector settings between operating systems just to make the display look similar.

## Common requirements

- 64-bit computer, Python 3.10 with tkinter and the project-pinned camera environment.
- One compatible EVK4 connected over USB 3 only when recording. The control window opens without a camera.
- Camera Python dependencies installed from `requirements.txt` in a separate project virtual environment. **Do not upgrade the working Mac environment to match Windows.** Use the same pinned package versions where wheels are available.
- Write recordings to a local or external disk, not into a live Google Drive sync folder. Each test produces original `events.evs`, raw/filtered/dashboard videos if capture succeeds, images, logs, `session.json`, `trial.json`, and index entries. Check integrity before uploading.

## macOS (existing tested development environment)

Launch controls from the repository root:

```bash
bash "Start EBS Tests.command"
```

For a Finder/Dock app, install once:

```bash
bash "Install EBS Desktop App.command"
```

Then open `~/Applications/EBS Field Tests.app`. The control window does not need the EVK4 plugged in. `Camera USB: CONNECTED` means enumeration only, not successful events. **START RECORDING** opens the unchanged EVK4 dashboard; **STOP & SAVE** sends the previously tested POSIX SIGINT request, then waits for the existing recorder to finish. Verify the output.

## Windows 11, x64 (requires local camera verification)

1. Install 64-bit **Python 3.10** with Tcl/Tk. Open Command Prompt and verify `py -3.10 -m tkinter` opens a test window.
2. Clone/download this repository and open it in File Explorer. **Double-click `Start EBS Tests.bat`**. No camera is needed to open the control form.
3. In Command Prompt, prepare a pinned camera environment once (in the repository root):

   ```bat
   py -3.10 -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   .venv\Scripts\python.exe -c "import neuromorphic_drivers as nd; nd.print_device_list()"
   ```

   Use a network connection for that first installation. If `.venv` is already configured, **do not reinstall or upgrade it**.
4. The Windows GUI checks `neuromorphic_drivers.print_device_list()` for EVK4 presence. This is a discovery check, not live streaming. If the camera is not listed, inspect Windows Device Manager and the USB driver. Prophesee documents EVK4 USB ID `04b4:00f5` and a Windows camera-driver setup. Do **not** replace USB drivers indiscriminately; follow the camera/vendor instructions, particularly on managed institutional PCs.
5. Run one **10-second target-free test**. Click **START RECORDING**. To finish an open-ended run early on Windows, **focus the unchanged EVK4 dashboard and press Q**. The controller watches the recorder exit and marks `FINISHED`. **The Windows Stop button only reminds you to press Q**, because sending POSIX SIGINT or Windows terminate would risk an incomplete file. For a fixed duration, it finalizes automatically. Never close the controller while finalization is underway.
6. Open the saved run and confirm original events, all expected videos, timestamps, settings, and `summary.json`. Flag `observed_input_loss`, missing media, and errors as incomplete. Test first on the actual Windows PC before using the data for cross-platform comparisons.

## Experimental controls, same on both systems

Enter measured environment, lens, range, fixed focus, aperture, illuminance (only if actually measured), light-source notes, target orientation, hover/crossing, repeat ID, and capture duration. Do not change `rotor_lab/rotor.py`, `activity.py`, `app.py`, or `settings.json` between conditions. Record target-absent intervals; press **1** for target present, **2** for target absent, **S** for native snapshot, and **Q** for normal dashboard shutdown. Tests conducted without an EVK4 only validate UI and software, not hardware throughput or detection performance.

**A positive activity flag is not proof of drone identity.** Compare matched target-associated activity, periodic evidence, missed/false cues, lighting, optics, and data loss; report these separately.

## Windows driver and API references

- `neuromorphic_drivers` 0.17.0 has Windows x64 Python 3.10 wheels: https://pypi.org/project/neuromorphic-drivers/0.17.0/
- Supported EVK4 in the cross-platform driver library: https://github.com/neuromorphicsystems/neuromorphic-drivers
- Prophesee EVK4 Windows 11 support and camera driver guidance: https://docs.prophesee.ai/stable/installation/windows.html
- Python Tkinter Windows/macOS: https://docs.python.org/3.10/library/tkinter.html
- Python subprocess signal differences: https://docs.python.org/3.10/library/subprocess.html

**Windows parity is not a physical test result.** Verify the driver, live acquisition, video encoding, normal Q shutdown, and saved-file integrity on your friend's machine before formal outdoor/indoor comparisons.
