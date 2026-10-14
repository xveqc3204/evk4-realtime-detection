#!/usr/bin/env bash
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON="${PYTHON:-python3}"
if [ ! -x .venv/bin/python ]; then
    "$PYTHON" -c 'import sys; assert (3,10) <= sys.version_info[:2] <= (3,13), "Use Python 3.10 to 3.13. Known Mac setup: Python 3.10.18."'
    "$PYTHON" -m venv .venv
fi
if ! cmp -s requirements.txt .venv/.rotor-requirements.txt; then
    .venv/bin/python -m pip install -r requirements.txt
    cp requirements.txt .venv/.rotor-requirements.txt
fi
case "${1:-}" in
    acceptance) shift; exec .venv/bin/python acceptance.py "$@" ;;
    check) shift; exec .venv/bin/python doctor.py "$@" ;;
    verify) shift; exec .venv/bin/python verify_run.py "$@" ;;
    stress) shift; exec .venv/bin/python stress_test.py "$@" ;;
    report) shift; exec .venv/bin/python report.py "$@" ;;
    test) shift; exec .venv/bin/python -m unittest discover -s tests -v "$@" ;;
    *) exec .venv/bin/python app.py "$@" ;;
esac
