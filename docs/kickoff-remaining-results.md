# Remaining kickoff checks — 2026-11-14

Minh accepted the existing response mapping (+1 Do, 0 Later, -1 No) and clothing override rules (manual persists until Auto). These are agreement confirmations, not new contract changes. The override implementation's prior test claim belongs to Tuan Anh; it was not rerun in this session.

Minh selected his Windows laptop as the intended hub host. `ipconfig` reported 192.168.0.143 on the current LAN. The board's camera-check dashboard at http://192.168.0.85:8000 loaded successfully in that laptop's Chrome, proving laptop-to-board HTTP access. These are observed DHCP addresses, not reservations. Hostname is still personalweather; pw-desk.local, reverse connectivity, hub port 8080, and reconnect after reboot remain unverified. The local hub folder currently contains only README.md.

## Camera calibration and shutter result

After correcting the USB topology (hub upstream to UNO Q, camera to hub data port, power to PD input), capture worked. Minh supplied screenshots of the completed measurements:

| Condition | Minimum | Mean | Maximum |
|---|---:|---:|---:|
| Normal desk light | 144.823125 | 147.353993 | 154.929167 |
| Dark room, shutter open | 149.201337 | 150.431321 | 152.416589 |
| Hand over lens | 0.861819 | 0.886518 | 0.902036 |
| Shutter closed | 0.719453 | 0.724423 | 0.731619 |

Threshold: **72.77737196180556**, halfway between shutter maximum and the lower uncovered minimum. Saved in `device/python/shutter.py`. The dark-room sample is brighter than the normal sample; this validates separation for the measured conditions only. Repeat in the darkest expected deployment lighting before claiming dark-room robustness.

The shutdown screenshot shows `camera: "shutter"`, `capture_open: false`, `level: null`, `error: null`, and 2014 frames. Minh confirmed reopening alone did not restart capture and clicking Camera on did restart it. These standalone dashboard checks PASS. The expected shutdown status is `shutter`, not `off`. Exact shutdown latency, physical camera LED, and restarting while the shutter remains closed were not separately recorded.

The production `vision.py` remains a stub; this test dashboard does not complete production integration. No images were added to git.

## Network follow-up

A fresh laptop `ipconfig` still reports **192.168.0.143**. Neither `pw-desk.local` nor `personalweather.local` resolved from the execution session. An HTTP check to the previously observed board address was blocked by local socket permissions; this is not evidence that the board is offline. Hostname setup and board-to-laptop HTTP remain unverified.

App Lab's dependency resolver rejected its vendor-specific OpenCV version when opencv-python-headless was requested, although the app then started with the preinstalled cv2. The source requirements file now uses that runtime-provided OpenCV; the imported copy still needs that comment-only requirements update before the next deployment.

Team chat channel name remains unknown. No messages or invitations have been sent.


App Lab was inspected again: the connected board still identifies as personalweather. Its live Python log confirms the final calibration values and three shutter-release events. No production integration pass is inferred from these logs.

## Latest verified network results (supersedes earlier pending notes)

Minh set hostname to pw-desk; board LAN address is 192.168.0.85. Avahi reported active. Chrome loaded http://pw-desk.local:8000 successfully: hostname discovery and laptop-to-board HTTP PASS. The earlier in-app browser name-resolution failure is not a board HTTP failure.

Board ping to Minh's laptop returned 2 sent, 0 received. Reverse HTTP is untested. Tuan Anh's laptop may host the hub instead; use its actual address and verify POST /summary. Reboot/rejoin remains pending. Team chat is skipped at Minh's request. Detailed owner-specific next steps: tuan-anh-handoff.md.
