#!/usr/bin/env bash
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# Reuse an existing environment. No dependency upgrades or automatic installs.
PY="${EVK4_PYTHON:-}"
IMPORTS='import numpy, numba, cv2, matplotlib'
if [ -z "$PY" ]; then
  for candidate in "$PWD/.venv/bin/python" \
    "$PWD/../.venv/bin/python" \
    "$HOME/Downloads/evk4_sep15_baseline/.venv/bin/python" \
    "$HOME/Downloads/evk4_rotor_lab_v03/.venv/bin/python" \
    "$HOME/Downloads/evk4_distance_test/.venv/bin/python" \
    "$HOME/Downloads/evk4_rotor_lab_v05/.venv/bin/python"; do
    if [ -x "$candidate" ] && "$candidate" -c "$IMPORTS" >/dev/null 2>&1; then
      PY="$candidate"; break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "No complete existing camera-processing environment found. No files changed."
  echo "Set EVK4_PYTHON to your working environment's absolute Python path."
  echo "For a NEW environment only, from the repository root:"
  echo "python3 -m venv .venv"
  echo ".venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi
if [ ! -x "$PY" ]; then
  echo "EVK4_PYTHON is not an executable Python path: $PY"
  exit 1
fi
"$PY" -c "$IMPORTS" || {
  echo 'This environment is missing a required package. No automatic updates were made.';exit 1;
}
exec "$PY" field.py "$@"
