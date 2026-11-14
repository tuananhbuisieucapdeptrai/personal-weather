# Arduino Project Hub page (draft, M5.3)

Publish at https://projecthub.arduino.cc/ → **+ NEW PROJECT** → tag **Junction Finland 2026**.
Fill the ⏳ items. Text can be pasted section by section.

## Title
Personal Weather: Edge AI desk companion for personal comfort and lower heating

## Short description
A privacy-first UNO Q desk companion. It learns how *you* feel in a shared office, suggests a free fix (put on a layer) before anyone asks for more heating, and helps the room agree on a lower setpoint. Camera images never leave the desk.

## Cover image
⏳ Photo of the device on a desk, LED face showing a smile or snowflake.

## Components and supplies
| Qty | Part |
|---|---|
| 1 | Arduino UNO Q (2 GB) |
| 1 | Modulino Thermo (temperature and humidity) |
| 1 | Modulino Knob (rotary encoder with push button) |
| 1 | Modulino Buzzer |
| 2–3 | Qwiic cables |
| 1 | USB webcam (UVC) |
| 1 | USB-C hub with power-delivery input |
| 1 | USB-C power supply |
| 1 | Laptop (room hub and dashboard) |
| — | Cardboard, tape; a strip of card as the camera shutter |

## Apps and platforms
Arduino App Lab · Python 3 (standard library) · OpenCV · ONNX Runtime

## Wiring
- **Modulinos:** Thermo, Knob and Buzzer are daisy-chained with Qwiic cables to the UNO Q's Qwiic connector (I²C, `Wire1`). Mount the **Thermo outside the case**, 10–15 cm from the board, because board heat skews readings.
- **Camera:**
  - The USB-C hub's upstream cable goes into the UNO Q.
  - The webcam goes into one of the hub's **data** USB-A ports, not a charge-only port.
  - The power supply goes into the hub's PD input.
- **LED face:** the UNO Q's onboard 13×8 matrix, no wiring.

⏳ Wiring photo.

## Story

### The problem
One thermostat serves people who feel the same room very differently. "I'm cold" usually means more heating for everybody.

### What it does
1. **Senses** temperature and humidity once per second (microcontroller → Linux over the App Lab Bridge).
2. **Predicts** how *this* person feels: a standard comfort formula (ISO 7730 PMV) plus a personal offset learned from knob feedback.
3. **Sees, privately:**
   - presence (face/body detector) and outer layer vs none (a MobileNetV3-Small classifier with ONNX Runtime, 45 ms on the UNO Q);
   - frames stay in memory;
   - a physical shutter stops capture.
4. **Suggests** a free fix on the LED face. The knob answers **DO / LATER / NO**, all optional. A follow-up later asks whether it helped.
5. **Shares minimally:** each desk sends a pseudonymous comfort summary to a laptop hub, which recommends the lowest heating setpoint that suits everyone. Nothing changes until someone clicks **Agree**.

### How the UNO Q is used
- **Microcontroller (STM32):** Modulinos, LED faces, buzzer, knob, with no blocking calls.
- **Linux (Qualcomm):**
  - vision in a separate process;
  - comfort model, suggestion engine and learning;
  - a local web API for the dashboard;
  - summaries to the hub.
- The two talk over the App Lab Bridge. Everything runs on the device, with no cloud.

### Results
- Clothing classifier: **37/40 = 92.5 %** on a separate held-out set of our own desk photos (two people; small test), reproduced on the board.
- Comfort formula: matches the reference library within **0.0009 PMV** over 522 conditions. One full estimate takes **3.1 ms** on the UNO Q.
- Personal model:
  - simulated (labelled): accuracy 0.48 → **0.73** for someone who runs cold;
  - live: ⏳.

### Privacy
Camera images never leave the desk. The hub receives only an anonymous ID, presence, comfort range and state. The dashboard shows the exact message sent.

### Energy, honestly
Three labelled layers: **Measured** (what the hub saw), **Proposed** (needs agreement), **Modelled** (research context: Hoyt, Arens & Zhang 2015). No saving percentage is claimed.

## Build steps
1. Connect the Modulinos with Qwiic, and the camera through the powered USB-C hub (see Wiring).
2. In Arduino App Lab, import the `device/` folder of the repo as an app. It publishes port 8000.
3. On the laptop, run `python3 hub/server.py`. On the board, in the app's `python/` folder, run `python3 summary.py --set-hub http://<laptop-ip>:8080`.
4. Start the app. Open `http://<laptop-ip>:8080/?device=http://<board>.local:8000` for the desk view and `/room` for the room view.
5. Build the case: LED and knob at the front, camera on top with a sliding card shutter, Thermo outside.

## Code
⏳ GitHub repository link (public).

## Team
Tuan Anh (software) · Minh (hardware)
