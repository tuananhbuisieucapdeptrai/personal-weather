#!/usr/bin/env bash
# Deploy device/ to the UNO Q app "personal-weather" and restart it (Tuan Anh).
#
# Always forces a sketch re-flash: if only the Python side restarts, the microcontroller's
# Bridge session does not reconnect and temperature readings stop (seen 2026-11-14).
# Runtime state (python/state: votes, models, pseudonyms, hub URL, demo flag) is kept.
#
#   tools/deploy_board.sh [user@host]        default arduino@pw-desk.local
set -euo pipefail
BOARD="${1:-arduino@pw-desk.local}"
APP=personal-weather
cd "$(dirname "$0")/.."

sed -i.bak "s|^// build: .*|// build: $(date +%Y-%m-%dT%H:%M:%S)|" device/sketch/sketch.ino && rm -f device/sketch/sketch.ino.bak

# Large CLIP model: copy only if missing or different (checksum).
L=$(shasum -a 256 device/python/models/clip_image.onnx | cut -c1-64)
R=$(ssh -o BatchMode=yes "$BOARD" "sha256sum ArduinoApps/$APP/python/models/clip_image.onnx 2>/dev/null | cut -c1-64" || true)
if [ "$L" != "$R" ]; then
  echo "uploading CLIP model (88 MB)..."
  cat device/python/models/clip_image.onnx | ssh -o BatchMode=yes "$BOARD" "cat > ArduinoApps/$APP/python/models/clip_image.onnx"
fi

COPYFILE_DISABLE=1 tar --no-xattrs --exclude 'python/state' --exclude '__pycache__' \
  --exclude 'python/models/clothing.ts' --exclude 'python/models/clip_image.onnx' -czf - -C device . \
  | ssh -o BatchMode=yes "$BOARD" "mkdir -p ArduinoApps/$APP && tar -xzf - -C ArduinoApps/$APP 2>/dev/null; \
      arduino-app-cli app stop user:$APP >/dev/null 2>&1; arduino-app-cli app start user:$APP 2>&1 | grep -E 'sketch updated|started|ERROR' | tail -2"

HOST="${BOARD#*@}"
for i in $(seq 1 40); do
  curl -s -m 2 -o /dev/null "http://$HOST:8000/state" && break; sleep 3
done
sleep 6
curl -s "http://$HOST:8000/state" | python3 -c "import json,sys; s=json.load(sys.stdin); e=s['env']; print('API up | labels', s['labels'], '| temperature', e['t'], 'samples', e['samples'])"
