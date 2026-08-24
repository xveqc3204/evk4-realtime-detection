# EVK4 Real-Time Activity Detection

Simple research code for using a Prophesee EVK4 event camera as a live activity detector.

The current code does not classify drones yet. It reads the EVK4 event stream live, checks for abnormal localized activity, and can raise a persistent `TARGET_ACTIVITY` flag.

## What works now

- EVK4 detected over USB 3 at 5 Gb/s
- Live asynchronous events from `neuromorphic_drivers`
- Event rate monitoring
- 5 ms live event chunks
- 32 x 18 spatial activity grid
- Short startup baseline calibration
- Local abnormal activity detection
- Real-time health checks for driver delay and backlog
- Simple persistent activity state and primitive tracking

Current flow:

```text
EVK4
  -> USB 3
  -> neuromorphic_drivers
  -> live (x, y, timestamp, polarity) events
  -> 5 ms chunks
  -> 32 x 18 activity grid
  -> compare against learned baseline
  -> candidate ROI
  -> persistence check
  -> TARGET_ACTIVITY = 1 or 0
```

## Tested setup

This project was developed on:

```text
macOS 15.1
Apple Silicon arm64
Python 3.10.18
Prophesee EVK4
neuromorphic_drivers 0.17.0
numpy 2.2.6
```

## Repo files

```text
camera_smoke_test.py
    Confirms the camera opens and prints live events per second.

live_activity_v01.py
    First live detector. Finds one abnormal localized ROI from 5 ms event chunks.

rt_test.py
    Runs the v0.1 detector headless and reports event rate, driver delay, backlog, and stale-data clears.

live_activity_v02.py
    Adds IDLE, PENDING, and ACTIVE states plus primitive ROI association and tracking.

requirements.txt
    Main Python dependencies.

requirements-viewer.txt
    Optional dependencies for the neuromorphic-drivers example viewer.

tools/patch_neuromorphic_viewer_macos.py
    Optional patch for the upstream example viewer when using PySide6 6.11.x on macOS.
```

## 1. Put the repo on your Mac

If you downloaded this project as a zip:

```bash
cd ~/Downloads
unzip evk4-realtime-detection.zip
mv evk4-realtime-detection ~/evk4-realtime-detection
cd ~/evk4-realtime-detection
```

If it is already in the folder you want, just `cd` into it.

## 2. Create the Python environment

From the repo folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

When the environment is active, Terminal should show `(.venv)` near the prompt.

Every time you open a new Terminal later:

```bash
cd ~/evk4-realtime-detection
source .venv/bin/activate
```

## 3. Plug in the EVK4

Plug the EVK4 directly into the Mac with a USB 3 capable cable.

Check that macOS sees it:

```bash
system_profiler SPUSBDataType
```

You want to see something similar to:

```text
EVK4
Manufacturer: Prophesee
Speed: Up to 5 Gb/s
```

Then check that the Python driver sees it:

```bash
python -c "import neuromorphic_drivers as nd; nd.print_device_list()"
```

You want to see the Prophesee EVK4 with USB 3.0 SuperSpeed.

## 4. Basic camera test

Run:

```bash
python camera_smoke_test.py
```

Move your hand in front of the camera.

The event rate should increase when something moves and decrease when the scene becomes still.

Stop with:

```text
Ctrl+C
```

## 5. Run v0.1 activity detection

Run:

```bash
python live_activity_v01.py
```

Keep the camera still for the first few seconds while it learns the normal activity in each region.

After calibration, moving something through the field of view should produce output like:

```text
*** CANDIDATE ACTIVITY DETECTED ***
time: 12085000 us | events: 9025 | score: 537.9
ROI: x=1000:1120, y=600:720
```

This means the code found a local area producing much more event activity than its learned baseline.

This is not drone classification. It is live abnormal activity detection.

## 6. Check whether the system is actually real time

Run:

```bash
python rt_test.py
```

Typical healthy output looks like:

```text
rate= 2.91 Mev/s | delay= 0.86 ms | backlog= 0 | clears=0
rate= 1.12 Mev/s | delay= 0.11 ms | backlog= 0 | clears=0
```

Important fields:

```text
rate
    Millions of decoded events per second.

delay
    Approximate software delay between incoming camera data and our Python consumer.

backlog
    Waiting driver data. We want this near zero.

clears
    Number of times stale queued data had to be dropped.
```

For real-time detection, low delay and low backlog are more important than processing every old event.

## 7. Run v0.2 persistent activity tracking

Run:

```bash
python live_activity_v02.py
```

Again, keep the camera still during startup calibration.

v0.2 adds three states:

```text
IDLE
  -> candidate appears
PENDING
  -> repeated nearby activity
ACTIVE
  -> TARGET_ACTIVITY = 1
```

Example:

```text
TARGET_ACTIVITY = 1
track_id: 4
ROI: (400, 240, 520, 360)
```

While active, the code prints occasional track center and velocity estimates.

When related activity disappears:

```text
TARGET_ACTIVITY = 0
reason: no_associated_activity
```

The current tracker is intentionally primitive. It follows the strongest abnormal patch, so its position and velocity can jump. That is a known limitation, not a finished object tracker.

## Optional live viewer

The detector does not need a rendered image. The viewer is only useful for understanding and debugging the event stream.

Install the optional GUI dependency:

```bash
python -m pip install -r requirements-viewer.txt
```

Clone the upstream driver repo next to this project or inside a temporary folder:

```bash
cd ~/evk4-realtime-detection
git clone --depth 1 https://github.com/neuromorphicsystems/neuromorphic-drivers.git
cd neuromorphic-drivers/python/examples
```

The PySide6 6.11.x example needed a small compatibility patch on the Mac used for this project. Run:

```bash
python ~/evk4-realtime-detection/tools/patch_neuromorphic_viewer_macos.py
python -m py_compile ui.py
python any_display.py
```

The viewer is optional. The headless detector is the important real-time path.

## What the code is doing

The camera produces asynchronous events rather than normal frames:

```text
(x, y, t, polarity)
```

The detector groups those events into 5 ms processing windows. It then bins the 1280 x 720 sensor into a 32 x 18 grid.

During startup it learns the mean and variance of normal event counts in each grid cell.

During operation it asks:

```text
Is one local part of the sensor much more active than normal?
```

If yes, it creates a candidate region of interest.

v0.2 then asks whether nearby candidate activity persists through several windows before raising the target activity flag.

## Current limitations

- It does not know whether the target is a drone.
- It currently chooses the strongest abnormal local patch.
- The v0.2 tracker can jump between different active parts of one object.
- Thresholds are experimental and still need tuning.
- Camera motion, lighting changes, background motion, and sensor noise still need more testing.

## Next development step

The next useful version is v0.3:

```text
active grid cells
  -> connected spatial clusters
  -> cluster bounding boxes and centroids
  -> associate clusters over time
  -> stable tracks
```

After stable tracking, drone-specific detection can be investigated using the raw event timing inside the tracked region.

## Git setup

To start tracking this folder with Git:

```bash
cd ~/evk4-realtime-detection
git init
git add .
git commit -m "Initial EVK4 real-time activity detector"
```

Create an empty repository on GitHub, then connect it. Replace the example URL with your repository URL:

```bash
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
git push -u origin main
```

After you change code later:

```bash
git status
git add .
git commit -m "Describe what changed"
git push
```

That is the normal loop for keeping the project updated.
