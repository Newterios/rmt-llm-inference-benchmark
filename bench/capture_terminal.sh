#!/usr/bin/env bash
# Opens a NEW Terminal window, runs a command in it, captures only that window to a PNG, closes it.
# Usage: bench/capture_terminal.sh "<shell command>" out.png <window height px>
set -euo pipefail
CMD="$1"; OUT="$2"; H="${3:-600}"
TMP=$(mktemp /tmp/capXXXX.sh)
printf 'cd /Users/aitbek/Desktop/AITU/rmt/rmt-llm-inference-benchmark\nclear\n%s\n' "$CMD" > "$TMP"
WID=$(osascript - "$TMP" "$H" <<'APPLESCRIPT'
on run argv
  tell application "Terminal"
    set w to do script ("bash " & item 1 of argv)
    delay 3
    set bounds of window 1 to {40, 60, 1240, (item 2 of argv as integer)}
    return id of window 1
  end tell
end run
APPLESCRIPT
)
sleep 1.5
screencapture -l "$WID" -o "$OUT"
osascript -e "tell application \"Terminal\" to close (every window whose id is $WID)" >/dev/null 2>&1 || true
rm -f "$TMP"
echo "captured $OUT (window $WID)"
