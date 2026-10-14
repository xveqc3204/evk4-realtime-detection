# Source and API inspection

Patch base: supplied evk4_sep15_baseline.zip. A separately supplied newer field.py
from ebs_test_setup.zip is accepted by the installer. Unknown local source is
not assumed identical. The original repository main is 596b89b and lacks this GUI;
Git import uses a new subdirectory and branch, preserving its original scripts.

Recorded September 15 setup: Python 3.10.18, macOS 15.1 arm64, NumPy 2.2.6,
Numba 0.61.2, OpenCV Python 4.12.0.88, neuromorphic_drivers 0.17.0,
Matplotlib 3.10.8. Requirements and camera APIs are not upgraded or replaced.

The EVT3 USB stream is decoded by the existing driver. The application's
structured records are (t uint64 microseconds, x/y uint16, on boolean), 13 bytes.
The application's EVK4DET1 .evs container is not native EVT3 RAW. Sensor microseconds
are never directly subtracted from Unix or monotonic host seconds. Recorded driver
delay is multiplied by 1000 for milliseconds, as in the existing data path.

Actual raw event recordings were not supplied. Supplied telemetry has ordered
sensor times consistent with 20 ms evaluations but does not verify the individual
event timestamps. The supplied run reports 4 clears/overruns and observed loss.

The existing filter is per-pixel ON/OFF run-start period estimation followed by
consistency, frequency-band and spatial-support rules. It is not a linear high-pass
filter. Default period output is regression-compared with archived rotor_v03.py.
Raw activity reads last_event before periodic filtering and ignores frequency.

Official references checked for APIs used by this patch:
- https://numba.readthedocs.io/en/0.61.2/user/jit.html
- https://numpy.org/doc/2.2/reference/generated/numpy.bincount.html
- https://raw.githubusercontent.com/opencv/opencv/4.12.0/modules/imgproc/include/opencv2/imgproc.hpp
- https://pypi.org/project/neuromorphic-drivers/0.17.0/
- https://raw.githubusercontent.com/neuromorphicsystems/neuromorphic-drivers/main/python/python/neuromorphic_drivers/status.py

The last driver source is upstream main, not proof of byte-identical installed
0.17.0 definitions. LiveSource and its already-used open/status/clear calls are
unchanged. New code uses existing NumPy/OpenCV/Numba only. All kernel variants are
warmed before opening USB; compilation is argument-type sensitive. This host could
not fetch the Mac/Python3.10 test environment. Runtime compatibility needs the
local test command, not an unsupported claim that it was tested here.
