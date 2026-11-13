#!/bin/bash
# One-time installer for a clickable app in ~/Applications.
# No application/detector/recording data is changed by this script.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
LAUNCHER="$ROOT/Start EBS Tests.command"
APP="$HOME/Applications/EBS Field Tests.app"
LOGDIR="$HOME/Library/Logs/EBSFieldTests"
if [ "$(uname -s)" != "Darwin" ]; then
  echo 'This installer must be run on macOS.' >&2
  exit 1
fi
if [ ! -f "$LAUNCHER" ]; then
  echo 'Missing GUI launcher; this is not the expected repo directory.' >&2
  exit 1
fi
if [ -e "$APP" ]; then
  echo "Application already exists: $APP" >&2
  echo 'No files overwritten. Move the existing app aside only if you want to reinstall.' >&2
  exit 1
fi
mkdir -p "$HOME/Applications" "$LOGDIR"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
# Literal, safe strings for AppleScript double-quoted values.
export EBS_GUI_LAUNCHER="$LAUNCHER"
export EBS_GUI_LOGDIR="$LOGDIR"
python3 - "$TEMP/run.applescript" <<'PY'
import os, sys
from pathlib import Path
p=Path(sys.argv[1])
def apple_quote(s):
    return '"' + s.replace('\\','\\\\').replace('"','\\"') + '"'
p.write_text('''on run\n'''
    + '    set launchFile to ' + apple_quote(os.environ['EBS_GUI_LAUNCHER']) + '\n'
    + '    set launchLog to ' + apple_quote(os.path.join(os.environ['EBS_GUI_LOGDIR'], 'launcher.log')) + '\n'
    + '''    try
        do shell script "/usr/bin/nohup /bin/bash " & quoted form of launchFile & " > " & quoted form of launchLog & " 2>&1 < /dev/null & echo started"
    on error errorText
        display dialog "Unable to open EBS GUI: " & errorText buttons {"OK"} default button 1
    end try
end run
''')
PY
/usr/bin/osacompile -o "$APP" "$TEMP/run.applescript"
echo "Installed clickable app: $APP"
echo "Launch with: open \"$APP\""
echo "If it doesn't open: open \"$LOGDIR\" and check launcher.log"
echo 'You may drag the app from ~/Applications into your Dock.'
