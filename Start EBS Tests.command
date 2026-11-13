#!/bin/bash
# Finder and Terminal launcher. Opens the control window even without the EVK4.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

is_gui_python() {
  [ -x "$1" ] && "$1" -c 'import sys, tkinter; assert sys.version_info >= (3,10)' >/dev/null 2>&1
}

PY=""
if [ -n "${EBS_GUI_PYTHON:-}" ]; then
  if is_gui_python "$EBS_GUI_PYTHON"; then PY="$EBS_GUI_PYTHON"; fi
else
  for candidate in \
    "$(command -v python3 || true)" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3" \
    "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3" \
    "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" \
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3" \
    "$ROOT/.venv/bin/python" \
    "$ROOT/rotor_lab/.venv/bin/python" \
    "$HOME/Downloads/evk4_distance_test/.venv/bin/python"; do
    if [ -n "$candidate" ] && is_gui_python "$candidate"; then
      PY="$candidate"
      break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "Could not find Python 3.10+ with Tkinter. Camera connection is NOT required."
  echo "Run: python3 -m tkinter"
  echo "Or set EBS_GUI_PYTHON to a Python with Tkinter installed."
  echo "No software was changed or recorded."
  exit 1
fi
exec "$PY" "$ROOT/rotor_lab/operator_gui.py"
