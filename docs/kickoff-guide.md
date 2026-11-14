# Kickoff guide: confirming the open decisions

How to check each item in the "Confirm at kickoff" list in [interfaces.md](interfaces.md). Each item has three parts:
- **Decide:** what to agree on at 08:00.
- **Verify:** the test that proves it works on the board.
- **Pass:** what you should see. Tick the box in `interfaces.md` only when the test passes.

| # | Item | Who | When | Time |
|---|---|---|---|---|
| 1 | Bridge mapping | Minh, Tuan Anh watching | M1.1 | ~20 min |
| 2 | Knob reset + response mapping | Agree 08:00 · Minh builds | M1.3 | ~15 min |
| 3 | Click sound | Minh | M1.3 | ~5 min |
| 4 | Camera shutter | Agree 08:00 · Minh builds | M2.4 / M3.1 | ~20 min |
| 5 | Clothing override | Agree 08:00 · Tuan Anh builds | T3.2 | ~5 min |
| 6 | Network + fixed IP | Both | 08:00–08:45 | ~20 min |
| 7 | Team chat | Both | 08:00 | 2 min |

## Quick start: kickoff helpers are in the repo

Minh's ordered run sheet, including Windows networking steps, is in
[minh-kickoff.md](minh-kickoff.md). Sensor/knob and Bridge checks are implemented,
but must still be compiled and verified on the board. LED drawing and the
production `vision.py` are not yet implemented. The standalone
`tools/kickoff/shutter_check.py` can test shutter capture/release after calibration;
dashboard restart still requires integration. Do not mark physical checks passed
based only on the presence of these files.

| Item | Run this | Where |
|---|---|---|
| 1–3 | Put `device/sketch/sketch.ino` and `device/python/*.py` into one App Lab app and click **Run**. `main.py` starts `board_check.py`, which prints PASS/FAIL for Bridge, env, faces, knob calibration and knob behaviour, and prompts you for each knob step. | UNO Q (App Lab) |
| 4 | `python3 tools/kickoff/shutter_calibrate.py`, then put the suggested value into `DARK_THRESHOLD` in `device/python/shutter.py` | UNO Q (SSH), or the laptop for a first estimate |
| 5 | `tools/kickoff/api_smoke.sh` | Laptop, once `api.py` exists (T3.2) |
| 6 | `bash tools/net/board_setup.sh` on the board, then `tools/net/laptop_check.sh` on the laptop | both |
| 7 | Create the chat group by hand | phones |

**How to get the files into App Lab:**
1. Create a new app called `personal-weather` in App Lab.
2. Replace its `sketch/sketch.ino` and `python/main.py` with the repo versions, and add the other `device/python/*.py` files next to `main.py`.
3. If App Lab asks for libraries, add **Modulino** and **Arduino_RouterBridge** to the sketch.
4. Afterwards, copy the generated `app.yaml` and `sketch/sketch.yaml` back into `device/` and commit them.

**If `board_check` says a knob calibration FAIL:** it prints the exact `#define` values to set. Change them in `sketch.ino`, upload again and rerun.

**After everything passes:**
- In `sketch.ino`, set `DEBUG_KNOB_RAW 0`.
- Leave `DEBUG_FACE_ACK 1` for now; it's harmless.
- In `main.py`, set `RUN_BOARD_CHECK = False` when Tuan Anh's real main loop arrives (T2.4).

---

## 1. Bridge function names

**What we now know.** This comes from community docs; the official reference is thin, so the test below is what really decides it.
- **Sketch → Python:** the sketch calls `Bridge.notify("name", args...)`. Python receives it with `Bridge.provide("name", fn)`.
- **Python → sketch:** Python calls `Bridge.notify("name", args...)` or `Bridge.call(...)`. The sketch receives it with `Bridge.provide` or `Bridge.provide_safe`.
- **`provide` vs `provide_safe` on the sketch:** a `provide` handler runs on a background thread, in parallel with `loop()`. A `provide_safe` handler runs between two passes of `loop()`. Anything that touches the Arduino API (LED matrix, buzzer, Serial) must use **`provide_safe`**.
- **`notify` vs `call`:** `notify` is fire-and-forget. `call` waits for an answer; from Python it times out after 10 s by default, and from the sketch it has **no timeout**.
- **Hard rules:**
  - Messages are limited to 256 bytes. Anything bigger is silently dropped.
  - Python Bridge handlers run on one dedicated thread and must not call `Bridge.call()`.
  - Sketch handlers must not call `Bridge.call()` or `Monitor.print()`, because that can deadlock.
  - `Bridge.begin()` blocks until the Linux side answers.

**Decide.** Use the table in `interfaces.md` 0.2.1:
- `notify` in both directions, so nothing ever blocks.
- The sketch registers its handlers with `provide_safe`.
- The sketch's `loop()` never calls `delay()`; use a `millis()` timer instead.

**Verify (Minh, M1.1).** Create a throwaway App Lab app with these two files.

`sketch/sketch.ino`:
```cpp
#include <Arduino_RouterBridge.h>

int faceCount = 0;
String lastFace = "";

void onFace(String name) { faceCount++; lastFace = name; }   // later: draw on the matrix

void setup() {
  Bridge.begin();
  Bridge.provide_safe("face", onFace);
}

unsigned long last = 0;
void loop() {                       // no delay() anywhere
  if (millis() - last >= 1000) {
    last = millis();
    Bridge.notify("env", 23.4, 41.2);          // float args
    Bridge.notify("knob_turn", -1);            // int arg
    Bridge.notify("knob_press");               // zero args
    Bridge.notify("face_ack", faceCount);      // proves Python -> sketch works
  }
}
```

`python/main.py`:
```python
import time
from arduino.app_utils import *

def on_env(t, rh):      print("env", t, rh, type(t))
def on_turn(pos):       print("turn", pos, type(pos))
def on_press():         print("press")
def on_ack(n):          print("sketch received face messages:", n)

Bridge.provide("env", on_env)
Bridge.provide("knob_turn", on_turn)
Bridge.provide("knob_press", on_press)
Bridge.provide("face_ack", on_ack)

def loop():
    Bridge.notify("face", "smile")
    time.sleep(1)

App.run(user_loop=loop)
```

**Pass when the App Lab console shows, every second:**
- `env 23.4 41.2 <class 'float'>` (not ints, not strings)
- `turn -1 <class 'int'>` (the negative number survives the trip)
- `press` (zero-argument notify works)
- `sketch received face messages:` followed by a count that goes up

**If something fails:**

| Symptom | Fix |
|---|---|
| The `String` parameter in `onFace` doesn't compile | Try `const char*`, or copy the signature from App Lab's own Bridge example |
| Zero-argument `notify` doesn't arrive | Send `Bridge.notify("knob_press", 1)` and ignore the value. `bridge_io.py` still produces `{"knob": "press"}`, so the contract doesn't change |
| Python → sketch `notify` doesn't arrive | Use `Bridge.call("face", name, timeout=1)` from Python. `send()` may then block for up to 1 s, so `main.py` sends faces from a worker thread |

If the names or argument types differ in any way, update the table in `interfaces.md` 0.2.1. That's the only place they're written down; `bridge_io.py` hides them from everyone else.

---

## 2. Knob: reset to 0 after press, and 0 = "Not now"

**Decide.** At 08:00, confirm these four rules:
1. The sketch keeps the position clamped to −1 / 0 / +1. It sends `knob_turn` only when the clamped value changes, so turning further right at +1 sends nothing.
2. **Clockwise = +1** (warm, arrow right, DO). Counter-clockwise = −1 (cold, arrow left, NO).
3. After every press, the sketch sets the position back to 0 without sending a message. Python assumes 0 too.
4. When a suggestion is answered, 0 = LATER ("Not now"). An accidental press is therefore the one answer with no consequences.

**One extra rule for Tuan Anh's `main.py` (no contract change).** A press counts as an answer only if the knob was turned at least once since the suggestion appeared. A press with no turn just shows the current choice ("LATER") on the face. This stops a bump on the knob from answering a suggestion that just popped up.

**Build (Minh, M1.3).** Sketch logic. The Modulino method names are from the Modulino library examples; check them against the Knob example in App Lab.
```cpp
#include <Modulino.h>
ModulinoKnob knob;

int lastRaw, pos = 0;
bool wasPressed = false;
unsigned long lastPressMs = 0;

void setup() {
  Bridge.begin();
  Modulino.begin(); knob.begin();
  lastRaw = knob.get();
}

void loop() {
  int raw = knob.get();
  int steps = (raw - lastRaw) / COUNTS_PER_DETENT;   // measure COUNTS_PER_DETENT, see below
  if (steps != 0) {
    lastRaw += steps * COUNTS_PER_DETENT;
    playClick();                                     // item 3
    int newPos = constrain(pos + steps, -1, 1);
    if (newPos != pos) { pos = newPos; Bridge.notify("knob_turn", pos); }
  }
  bool pressed = knob.isPressed();
  if (pressed && !wasPressed && millis() - lastPressMs > 200) {   // edge + debounce
    lastPressMs = millis();
    Bridge.notify("knob_press");
    pos = 0;                                         // reset, no message
  }
  wasPressed = pressed;
}
```

**Before writing that code:** print `knob.get()` while turning exactly one click.
- Write down how many counts one click produces. That number is `COUNTS_PER_DETENT`.
- Write down which direction makes the count go up. If clockwise makes it go *down*, flip the sign of `steps`.

**Verify:**

| Do this | Expect exactly |
|---|---|
| Turn 3 clicks clockwise | `turn 1`, then nothing more |
| Turn 1 click counter-clockwise | `turn 0` |
| Press | `press`. Then 1 click clockwise gives `turn 1`, which shows the position was reset to 0 |
| Press and hold for 2 s | Exactly one `press` |
| Spin fast in both directions | Every value is −1, 0 or 1, and none is missed |

---

## 3. Click sound played by the sketch

**Why.** A click sent through Python would lag behind the turn by a full Bridge round trip. In the sketch it is instant and costs no messages.

**Build (Minh).** Write a `playClick()` function with three rules:
- **Short and high**, e.g. `buzzer.tone(4000, 5)`. Check that `tone` doesn't block. If it does, keep the duration at 5 ms or less.
- **Rate-limited** to at most one click every 40 ms, so a fast spin doesn't buzz continuously.
- **One click for every detent**, even at the −1/+1 limits. The user still feels the turn even though no message is sent.

**Verify:**
- Turn slowly and you hear a click per detent.
- Spin fast and you hear a soft rattle, not a continuous tone.
- The Python console shows nothing new except `turn` messages.

**Decide:** is the click annoying in a quiet office? If yes, the fallback is no click at all. In that case, delete it from the face table in `interfaces.md`.

---

## 4. Camera shutter: stops, and restarts only from the dashboard

**Why no automatic restart.** Detecting that the shutter has reopened means grabbing frames while it is closed. Then the privacy receipt couldn't honestly say "no capture while the shutter is closed". The cost is one extra press of "camera on" on the dashboard. In the demo the shutter is step 7, the last step, so this costs nothing on stage.

**Decide at 08:00:**
1. Dark frames for ~3 s stop capture and set the status to `"shutter"`. The camera device is released, so the camera's own LED goes off as physical evidence.
2. Capture restarts only from `POST /control {"camera": "on"}`, which calls `vision.start()`.
3. If the shutter is still closed when the camera is turned back on, the status goes back to `"shutter"` after 3 s. This is expected.

**Calibrate (Minh, M2.4).** The threshold must separate a **closed shutter** from a **dark room**. Log the mean grey level for each condition:
```python
gray_mean = frame.mean() if frame.ndim == 2 else frame.mean(axis=2).mean()   # numpy, 0..255
```

| Condition | Mean (0–255) |
|---|---|
| Normal desk light | _____ |
| Room lights off / evening | _____ |
| Hand over the lens | _____ |
| **Shutter closed** | _____ |

- Set `DARK_THRESHOLD` halfway between "shutter closed" and the darkest real scene.
- Require every frame for 3 s to be below the threshold, not just an average, so one dark frame doesn't trigger it.

**Pass when:**
- Shutter closed → within ~3–4 s, vision reports `{"present": null, "clothing": "uncertain", "conf": null, "camera": "shutter"}`.
- The camera LED goes off.
- `ps` shows no capture loop running.
- Room lights off with the shutter open still reports `"on"`.
- Pressing "camera on" with the shutter open gives `"on"` again.

---

## 5. Clothing override in `/control`

**Why.** If the classifier fails the 14:00 gate, the plan says clothing is set on the dashboard. That needs a field in the contract. It is already in `contracts.py`:
```json
{"clothing": "outer"}   {"clothing": "none"}   {"clothing": "auto"}
```

**Decide at 08:00:**
1. **Priority:** `outer` or `none` overrides whatever vision says. `auto` means vision decides; this is the default.
2. **The override sticks** until someone sets `auto`, including across profile switches. While it is active, the dashboard shows a "CLOTHING: SET MANUALLY" label, following the labelling rule in 0.3.
3. **If the gate fails, `vision.py` keeps running for presence and shutter detection.** Only the clothing classifier is switched off, and it reports `"uncertain"`. Demo step 7 (shutter) still works.
4. **Follow-up after "Do it" while the override is active:** the "camera confirms the layer" step becomes "the person confirms on the dashboard", and it is labelled that way. Same honesty rule as everything else.

**Verify (Tuan Anh, T3.2):**
```bash
curl -s -X POST http://pw-desk.local:8000/control -H 'Content-Type: application/json' -d '{"clothing":"outer"}'
```

```bash
curl -s -X POST http://pw-desk.local:8000/control -H 'Content-Type: application/json' -d '{"clothing":"jacket"}'
```

**Pass when:**
- The first command returns `/state` with the override active.
- The second command returns 400 with the contract error.

---

## 6. Network: hotspot, hostname, fixed IP

**Use a phone hotspot, not the Mac.** macOS Internet Sharing cannot share Wi-Fi *to* Wi-Fi while the Mac itself is on Wi-Fi. Venue Wi-Fi often blocks device-to-device traffic, which is why the plan wants your own hotspot.

**Steps (08:00–08:45, both):**
1. **Turn on a phone hotspot.**
   - On an iPhone, also turn on **Maximize Compatibility** (2.4 GHz), which is the safest option for the board.
   - Don't put the SSID or password in the repo.
2. **Laptop joins the hotspot.** Find its address:
   ```bash
   ipconfig getifaddr en0
   ```
   This is the hub address.
3. **Board joins the hotspot** using App Lab's network setup on first boot.
4. **Set the hostname.** Open a shell on the board (App Lab terminal, or SSH):
   ```bash
   sudo hostnamectl set-hostname pw-desk && sudo reboot
   ```
   After the reboot, run `hostname -I` on the board and note its IP.
5. **Test both directions.**
   - On the laptop: `ping pw-desk.local`.
   - On the board: `ping <laptop-ip>`.
6. **Fixed IP (fallback only).** Phone hotspots usually give the same device the same IP again, so first just **write the observed IP** into `interfaces.md` 0.3.
   - Set a static IP only if `.local` stops resolving at the venue.
   - Only do this if `nmcli` exists on the board.
   - The example is for iPhone hotspots, which use 172.20.10.0/28 with the gateway at .1:
   ```bash
   nmcli -t -f NAME,DEVICE con show --active
   ```
   ```bash
   sudo nmcli con mod "<connection-name>" ipv4.method manual ipv4.addresses 172.20.10.12/28 ipv4.gateway 172.20.10.1 ipv4.dns 172.20.10.1 && sudo nmcli con up "<connection-name>"
   ```
   If the board drops off the network after this, undo it with `ipv4.method auto`. Better to do that over a USB connection, not Wi-Fi.
7. **macOS firewall.**
   - The first time the hub listens on port 8080, macOS asks whether to allow incoming connections for Python. Click **Allow**.
   - If the board can ping the laptop but can't reach port 8080, check System Settings → Network → Firewall.
8. **Set the hub URL** on the board for `summary.py`:
   ```bash
   export PW_HUB_URL=http://<laptop-ip>:8080
   ```

**Note:** while the laptop is on the hotspot, its internet uses the phone's data. Git pushes are fine; avoid big downloads.

**Pass when:**
- Both pings work.
- The IP and hostname are written into `interfaces.md` 0.3.
- After rebooting the board, it rejoins the hotspot by itself (this check belongs to M4.2).

---

## 7. Team chat channel

- Make a two-person group in any app you both have open all weekend (Telegram, Discord, Messenger…). Write the name into `interfaces.md` 0.3.
- **Pin** the repo URL, `docs/interfaces.md`, and the sync times (11:00, 14:00, 17:00, 21:00, 01:30, Sunday 09:30).
- Blocked-message format, so the 30-minute rule is quick to act on:
  > **BLOCKED** since 10:20 on *Bridge float args* · tried: const char*, call() · need: 10 min of your eyes

---

## After kickoff

1. Tick every box in `interfaces.md`.
2. Fill in the two blanks: the team chat and the board's IP.
3. Commit (`git add -A`, then `git commit -m "Kickoff: confirmed interfaces"`), then `git push`.
