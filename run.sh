#!/usr/bin/env bash
# Single repository entry point. Camera code and data remain in rotor_lab/.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec bash "$ROOT/rotor_lab/test.sh" "$@"
