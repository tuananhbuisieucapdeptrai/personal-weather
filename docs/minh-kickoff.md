# Minh's kickoff checklist

Based on spec v5, interfaces.md and kickoff-guide.md. This is a run sheet,
not evidence that the physical tests have passed.

## 1. Connect and run (kickoff items 1–3)

1. Connect Thermo, Knob and Buzzer using the kit's Qwiic cables with power off.
   Mount Thermo away from board heat. Connect the USB camera through the hub.
2. Open Arduino App Lab, connect the UNO Q and create `personal-weather`.
3. Copy `device/sketch/sketch.ino` into the app's sketch and every file from
   `device/python/` into its Python folder. Keep the generated App Lab metadata;
   copy `app.yaml` and `sketch/sketch.yaml` back to the repo after a successful run.
4. Resolve libraries using the installed App Lab examples. The existing sketch
   uses `Modulino.h` and `Arduino_RouterBridge.h`; record the working versions.
5. Keep `RUN_BOARD_CHECK = True`, `DEBUG_KNOB_RAW 1`, `DEBUG_FACE_ACK 1`.
6. Click Run. Follow each ten-second knob prompt exactly. Save the console output.
7. If calibration fails, apply the printed `COUNTS_PER_DETENT` and
   `KNOB_DIRECTION` values, upload again and rerun. The checker now compares
   against settings reported by the running sketch, rather than defaults.
8. Listen for the click during slow and fast turns. Confirm one press during a
   two-second hold. A Bridge acknowledgment proves receipt, not visible drawing:
   the sketch still has a TODO for LED rendering (M2.1).
9. Only after physical checks pass, set `DEBUG_KNOB_RAW 0` and record results.
   Keep the kickoff main loop until Tuan Anh's real loop is ready.

Expected mapping:

| Movement | Position | Comfort | Suggestion |
|---|---:|---|---|
| Counter-clockwise | -1 | Cold | Not possible |
| Middle / reset after press | 0 | OK | Not now |
| Clockwise | +1 | Warm | Do it |

Agree with Tuan Anh that an answer requires a turn after a suggestion appears.
Python owns smoothing; the sketch sends raw temperature/humidity at 1 Hz.

## 2. Prove shutter shutdown (item 4)

Stop any other app using the camera. In a terminal on the UNO Q, from the repo root:

```bash
python3 tools/kickoff/shutter_calibrate.py
```

Measure normal light, the darkest realistic room, a covered lens and the closed
physical shutter. If ranges overlap, improve the shutter and repeat. Put the
suggested value into `device/python/shutter.py`, then run (replace 12):

```bash
python3 tools/kickoff/shutter_check.py --threshold 12
```

- Keep the shutter open in the dark room: capture should continue.
- Close it: after about three seconds of dark frames, capture is released.
- Confirm the camera LED turns off if the camera has a capture indicator.
- Open it without pressing Enter: capture must remain stopped.
- Press Enter: this explicitly restarts capture. Repeat with shutter still closed.

This standalone check validates capture/release and the threshold. It does **not**
complete `vision.py`, person detection, clothing inference or dashboard restart.
Those remain M2.4/M3.1 and require a further integration test. A live Python
process waiting for input is normal; it does not mean the camera is capturing.
Describe shutdown honestly: capture stops after detection, not instantly when
the shutter closes. Darkness alone cannot prove a physical shutter is closed.

## 3. Network on your Windows laptop (item 6)

Join the same private hotspot as the board. In PowerShell:

```powershell
Get-NetIPConfiguration
ping pw-desk.local
Test-NetConnection pw-desk.local -Port 8000
```

Use the Wi-Fi IPv4 address as the hub address only if this laptop runs the hub.
If Tuan Anh's laptop runs it, use his laptop's address instead. If `.local` fails,
get `hostname -I` from the board terminal and retry using that IP. Port 8000 is
expected to fail until Tuan Anh starts the API; this alone is not a Wi-Fi failure.
The existing `laptop_check.sh` is for macOS, not PowerShell.

On the board, once the hub runs on port 8080:

```bash
ping -c 2 <hub-laptop-ip>
export PW_HUB_URL=http://<hub-laptop-ip>:8080
```

Replace placeholders with observed addresses. Test an actual hub request too;
ping alone does not prove HTTP connectivity. Allow the hub through the laptop's
private-network firewall if needed; do not disable the firewall. Retain DHCP
unless there is a demonstrated need for a static address. An observed IP is not
a reserved/fixed IP. Record it and recheck after a reboot.

## 4. Joint decisions and handoff (items 5 and 7)

- Agree clothing override values `outer`, `none`, `auto`; Tuan Anh implements
  the API, visible manual label and follow-up behavior.
- Agree the chat channel and record its name together. Pin the repo and sync times.
- Share board-check output, knob settings, shutter measurements, board IP and
  library versions with Tuan Anh. Do not share hotspot credentials in git.
- Tick only the corresponding verified boxes in `interfaces.md` together.
  Do not tick all boxes merely because the scripts exist.

## Remaining physical evidence

| Item | Status / evidence to record |
|---|---|
| App Lab uploads and starts | PASS on UNO Q, App Lab 0.12.0 / platform 1.1.0 |
| Thermo / Knob / Buzzer detected | PASS: all three detected |
| Bridge both directions | PASS: 1 Hz environment messages and 17/17 commands acknowledged |
| Knob counts and direction | PASS: 1 count per notch, clockwise positive |
| Clamp, reset, hold and click | Automated behaviour PASS; Minh confirmed separate slow clicks and repeated clicks on fast turns. Office volume acceptance remains open; no sound changes requested after API limitation explained. |
| Shutter threshold and release | PASS in standalone camera app: threshold 72.7774; shutter status and capture release shown in screenshot; Minh confirmed no automatic restart and successful explicit restart. Dark-room robustness and closed-shutter restart need separate checks. |
| Dashboard camera restart and override | Pending teammate API and vision integration |
| Network both directions | Laptop to board PASS by IP and pw-desk.local in Chrome. Reverse HTTP to intended hub and reboot/rejoin pending. |
| Team channel | Skipped at Minh's request |

After kickoff, your next tasks are LED rendering, the production camera pipeline,
consented clothing sessions and classifier evaluation. Preserve the plan's 14:00
vision gate: if it fails, use manual clothing and retain presence/shutter work.
