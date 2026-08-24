"""Patch the neuromorphic-drivers example viewer for PySide6 6.11.x on macOS.

Run this from the cloned neuromorphic-drivers/python/examples directory.
It creates ui.py.bak before changing ui.py.
"""

from pathlib import Path
import re
import shutil

p = Path("ui.py")
if not p.exists():
    raise SystemExit("Run this script from neuromorphic-drivers/python/examples")

backup = Path("ui.py.bak")
if not backup.exists():
    shutil.copy2(p, backup)

s = p.read_text()

# PySide6 6.11 added fdel before doc in the Property positional signature.
pattern = re.compile(
    r'(PySide6\.QtCore\.Property\(\n(?:        [^\n]+,\n){4})        ("[^"\n]*"),'
)
s, n1 = pattern.subn(r'\1        doc=\2,', s)

# Add a readable sensor_size getter if this version of ui.py only has a setter.
if "def get_sensor_size" not in s:
    old = "    def set_sensor_size(self, sensor_size: PySide6.QtCore.QSize):\n"
    new = (
        "    def get_sensor_size(self) -> PySide6.QtCore.QSize:\n"
        "        if self._sensor_size is None:\n"
        "            return PySide6.QtCore.QSize()\n"
        "        return self._sensor_size\n\n"
        "    def set_sensor_size(self, sensor_size: PySide6.QtCore.QSize):\n"
    )
    if old in s:
        s = s.replace(old, new, 1)

s = s.replace(
    "        PySide6.QtCore.QSize,\n        None,\n        set_sensor_size,\n",
    "        PySide6.QtCore.QSize,\n        get_sensor_size,\n        set_sensor_size,\n",
    1,
)

old_guard = '''        if self._sensor_size is None:\n            raise Exception(\n                'the sensor size must be set in QML (for example, EventDisplay {sensor_size: "1280x720"})'\n            )\n'''
if old_guard in s:
    s = s.replace(old_guard, "        if self._sensor_size is None:\n            return\n", 1)

p.write_text(s)
print(f"Patched ui.py. Property doc fixes: {n1}")
print("Backup: ui.py.bak")
