# Minh to Tuan Anh: kickoff handoff

2026-11-14. Hardware bring-up is verified; production integration is not complete.

## 1. Receive the work

After Minh's commit is pushed, save/commit your own work and run `git pull --rebase origin main`. Preserve your newer main-loop and hub work when resolving conflicts. Read kickoff-board-results.md and kickoff-remaining-results.md for evidence.

Delivered changes: explicit UNO Q Wire1 selection; independent raw encoder tracking; calibration against settings reported by the sketch; WARN/SKIP reporting; calibrated shutter threshold; standalone CLI and App Lab camera tests; App Lab metadata and pinned sketch dependencies; hardware results and Windows instructions.

Root ZIP files are old generated snapshots, not authoritative sources. Rebuild imports from device/ or tools/kickoff/camera_app/, putting app.yaml at the archive root. Do not commit local .codex configuration, camera images, datasets, credentials or runtime state.

## 2. Verified baseline

| Area | Evidence |
|---|---|
| Board | UNO Q; App Lab 0.12.0; zephyr platform 1.1.0 |
| Libraries | Arduino_Modulino 0.9.0; transitive dependencies in device/sketch/sketch.yaml; RouterBridge supplied by platform |
| Modules | Thermo, Knob and Buzzer detected with Modulino.begin(Wire1) |
| Sensors | Raw temperature/humidity at 1 Hz with decimals preserved |
| Bridge | 17/17 Linux-to-sketch commands acknowledged |
| Knob | All 13 automated board checks passed; 1 count/notch, clockwise positive; clamp/reset/hold/fast-turn checks passed |
| Sound | Individual slow clicks and repeated fast clicks; unchanged; quiet-office acceptance still open |
| Camera | USB camera on hub attached upstream to UNO Q, with PD power; laptop controls board over Wi-Fi |
| Calibration | DARK_THRESHOLD = 72.77737196180556 in device/python/shutter.py |
| Shutter test | camera=shutter, capture_open=false; reopening does not restart; explicit Camera on restarts |
| Network | Hostname pw-desk; Chrome loads http://pw-desk.local:8000; DHCP IP 192.168.0.85, not reserved |

Acknowledgments prove message receipt, not LED rendering. Standalone camera results do not prove production vision or clothing classification. The dark-room sample was brighter than normal: repeat in the darkest intended deployment lighting.

## 3. Run the hub on your laptop (Tuan Anh)

Your laptop can host the hub; Minh's laptop is not required. Join the same network as UNO Q. Find your active Wi-Fi IPv4 address using Windows ipconfig or macOS network settings. Do not reuse Minh's 192.168.0.143 unless his laptop runs the server.

Merge or implement your server: the inspected checkout has only hub/README.md. Document its actual launch command. Bind to 0.0.0.0:8080 or your LAN interface, not only localhost. Serve the dashboard and implement POST /summary using the C8 contract, returning HTTP 204. If necessary, allow this application on the trusted/private network; do not disable the firewall.

On UNO Q, substitute your real laptop address and test a valid request against a test hub instance:

```bash
curl -i --connect-timeout 3 --max-time 5 \
  -H 'Content-Type: application/json' \
  -d '{"pid":"p-a001","present":false,"mode":"heating","band_now":[21.0,22.5],"state":0,"unresolved":false}' \
  http://YOUR_LAPTOP_IP:8080/summary
```

Expect 204 plus a matching receipt in server logs. This is synthetic test data, not a measured person: remove the entry afterwards or let it expire, and do not present it as LIVE evidence. A timeout/refusal needs service, binding, firewall or network diagnosis. Minh's failed ICMP ping does not establish HTTP failure.

Set PW_HUB_URL=http://YOUR_LAPTOP_IP:8080 in the actual device application's environment. An SSH `export` changes that shell and its children only, not an already-running App Lab container. Verify the effective URL from the running sender, restart the application, and confirm the setting persists.

Stamp receipt time on the hub. Summaries older than two minutes become stale/absent. Keep profiles separate and use pseudonyms, not names or images. Distinguish simulated entries in the dashboard.

## 4. Integrate your real main loop (Tuan Anh)

device/python/main.py currently runs board_check with RUN_BOARD_CHECK=True. Setting it False alone does not start a production app: merge/implement the real entry point first.

1. Register bridge_io.start with a callback that only enqueues messages. Process the queue in the main loop; no blocking operations or Bridge.call inside callbacks.
2. Smooth temperature/humidity in Python, preserving raw sketch readings. Mark readings stale after more than five seconds without valid environment data.
3. Keep knob positions -1/0/+1. After a press, reset the Python selection to zero to match the sketch's silent reset.
4. Map suggestions +1=DO, 0=LATER, -1=NO. Require a turn since the suggestion appeared before a press answers it; a press without a turn only previews LATER.
5. Wire comfort, suggestions, API state and summaries. Use bridge_io.send for face/beep messages. Clicks remain local to the sketch.
6. Send one summary per profile every 60 seconds and on changes. Only the active profile may be present. Omit band_with_fix when no feasible fix exists. Validate with contracts.py.
7. Disable RUN_BOARD_CHECK only after production startup works. Disable DEBUG_KNOB_RAW for production; re-enable it for calibration tests. DEBUG_FACE_ACK may remain during integration.

## 5. Coordinate vision with Minh; wire API controls (joint)

Minh still owns vision.py, LED rendering and classifier work. They are not transferred to you by this handoff. vision.py currently raises NotImplementedError. Coordinate readiness before calling it from the production loop.

Required functions: vision.start(), vision.stop(), vision.latest(). Off/shutter must report unknown evidence: present=null, clothing=uncertain, conf=null, camera=off or shutter. Do not invent presence or clothing values.

Stop the standalone camera app before production: it owns the camera and port 8000. Its control body is {"action":"on"}, not the production {"camera":"on"}. It is not a replacement for api.py.

Production POST /control camera on/off should call vision.start/stop and return current state. No automatic polling capture after shutter release. Show actual camera status on the dashboard. Describe privacy accurately: capture stops after sustained darkness (~3 seconds), not instantaneously when the shutter moves.

Start with the calibrated shutter.py threshold, then jointly retest darkest expected lighting. Keep images only in memory. The camera-check requirements.txt uses runtime-provided cv2; do not request the Arduino vendor-specific OpenCV version from PyPI. Update the imported test app's old requirements on the next deployment.

## 6. Verify clothing override and dashboard (Tuan Anh)

Minh accepted outer/none/auto. Manual outer or none overrides vision until auto, including across profile changes. Show CLOTHING: SET MANUALLY. In manual mode, the person confirms the layer on the dashboard; do not label it camera-confirmed. If classification fails the vision gate, preserve presence/shutter work and return uncertain clothing with the manual fallback.

Run `bash tools/kickoff/api_smoke.sh pw-desk.local:8000` only against production (Bash/WSL/Git Bash, or on UNO Q with 127.0.0.1:8000). It changes mode/override and switches camera off/on, so coordinate the run. Expect 11 checks passing. These check HTTP status codes only: separately verify override persistence across profiles, auto restoration, visible labels and follow-up behavior.

## 7. Joint acceptance before declaring integration complete

- Verify freshness/smoothing, knob response mapping, visible LED faces and sound.
- Open shutter in darkest expected room: capture stays on.
- Close shutter: time release (~3-4 seconds), check shutter status and camera indicator if present.
- Reopen without a command: no capture. Explicit on resumes. Explicit on while still closed shuts down again.
- Repeat camera and clothing controls on the production dashboard.
- Verify summary POST/204, heartbeat/change delivery, profile separation and stale-after-two-minutes behavior.
- Reboot after saving results: confirm network rejoin, hostname/IP, app startup and configured hub URL. Recheck DHCP addresses.
- Decide quiet-office sound acceptance. Team-chat setup is skipped at Minh's request.

Do not tick end-to-end checklist boxes solely because a diagnostic test passed. Pushes of this work represent a verified kickoff baseline, not a completed product.
