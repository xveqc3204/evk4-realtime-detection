#!/usr/bin/env bash
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# Reuse the established environment without updating packages.
PY="${EVK4_PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in "$PWD/.venv/bin/python" \
    "$HOME/Downloads/evk4_rotor_lab_v03/.venv/bin/python" \
    "$HOME/Downloads/evk4_distance_test/.venv/bin/python" \
    "$HOME/Downloads/evk4_rotor_lab_v05/.venv/bin/python"; do
    if [ -x "$candidate" ]; then PY="$candidate"; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "No existing camera environment found. Run once while online:"
  echo "python3 -m venv .venv"
  echo ".venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi
"$PY" -c 'import numpy, numba, cv2, matplotlib' || {
  echo 'This environment is missing a required package. No automatic updates were made.';exit 1;
}
exec "$PY" field.py "$@"
