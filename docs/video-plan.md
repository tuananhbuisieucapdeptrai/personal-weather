# Demo video plan (~2 min)

**Goal:** in two minutes, a judge sees:
1. a **real device** working **live**;
2. the **personal + perceptive + adaptive** loop;
3. the **energy logic** (a layer instead of heating, so a lower room setpoint);
4. **privacy**: no images leave the desk, and the shutter turns the camera off.

Everything shown is live, except the coworkers, which are labelled **SIM**, and the follow-up timer, which is labelled **Sped up**.

---

## Before you press record (5 min)

**The device**
- [ ] The app is running. The dashboard header says **Live · Sped up · 📷 on**, and a temperature is shown.
- [ ] The camera shutter is **open**. The camera faces your **chest** from where you sit, about 60–80 cm away.
- [ ] The Thermo hangs **outside**, away from the board and the laptop.
- [ ] LED face visible (a smile when you sit down). Knob within reach.

**The laptop**
- [ ] Tab 1: `http://localhost:8080/`, the desk view. **Person = Tuan Anh, Wearing = Camera, Season = Heating.**
- [ ] Tab 2: `http://localhost:8080/room`, the room view, with coworkers **hidden** to begin with.
- [ ] Browser zoom about 125 %, so the phone can read it. Notifications off.

**You**
- [ ] **No jacket** on. A **zip-up jacket** within reach, ideally a dark or clearly visible one. Zip it fully; open jackets aren't recognised.
- [ ] Practise once: keep the jacket **away from the lens** while putting it on.

**Filming**
- [ ] Phone in landscape, on a stand if possible. Frame the **device and the laptop screen** together, or cut between them.
- [ ] A quiet room. Speak slowly. One take is fine; cut later if needed.

**Don't restart anything once you're happy with the setup.** A restart can drop the temperature reading; if it happens, run `tools/deploy_board.sh` again.

---

## Shot list

| # | Time | On screen / action | Say (roughly; your own words are fine) |
|---|---|---|---|
| 1 | 0:00–0:12 | Wide shot: you at the desk, the device with its LED smile | "In a shared office, one thermostat serves people who feel the same room very differently. 'I'm cold' usually means more heating for everyone." |
| 2 | 0:12–0:25 | Close-up of the device, then the dashboard header: **Live**, temperature, "Wearing: no layer" | "Personal Weather is an edge-AI desk companion on the Arduino UNO Q. Live temperature and humidity, and a camera that recognises whether I'm wearing a layer. Everything runs on the device. Images never leave it." |
| 3 | 0:25–0:35 | Dashboard: the two numbers ("answers predicted right") | "It predicts how *I* feel with a standard comfort model, corrected by what it has learned about me." |
| 4 | 0:35–0:50 | **One click left → press.** The LED shows a snowflake, then the **layer icon blinks with a chime**. Dashboard: **"Put on a layer · instead of more heating"** | "I tell it I'm cold. Instead of asking for more heat, it suggests a free fix. It's optional: I could say later, or not possible." |
| 5 | 0:50–1:05 | **Put the jacket on and zip it** (away from the lens). The device gives a **✓ and a chirp by itself**. Dashboard: "Wearing: a layer", "Checking in 30 s" | "I don't even need to answer: the camera sees me put on the layer. In a moment it'll ask whether it helped." |
| 6 | 1:05–1:20 | While waiting: point at the **privacy line**, click **"What is sent"** | "This is everything that leaves my desk: an anonymous ID and a comfort range. No name, no images." |
| 7 | 1:20–1:30 | LED: **"did it help?"** with a chime. **Press once** (OK). "Helped" count goes up | "It did. It keeps an honest record of what works for me, and it learns over time." |
| 8 | 1:30–1:50 | **Room tab.** Click **Show** coworkers (SIM tags visible). "**Set heating to 20.0 °C**" plus the comfort-range chart. Click **Agree** | "Each desk sends only that small summary. Because people can fix their own comfort, the room can run 1.5 °C cooler, and everyone is still OK. Nothing changes until a person agrees. The coworkers here are simulated." |
| 9 | 1:50–2:00 | Scroll to **Energy**: Measured / Proposed / Modelled | "We show energy honestly: measured, proposed, and modelled from research, with no invented percentage." |
| 10 | 2:00–2:10 | **Close the shutter**: eye-off face, low beep; dashboard shows "📷 covered". End on the device | "Close the shutter and the camera stops. The cheapest kilowatt-hour is a jacket." |

Total: about 2:10. If it runs long, shorten shots 3 and 6.

---

## If something goes wrong while filming

| Problem | What to do |
|---|---|
| No suggestion after the cold vote | Check "Wearing" says **no layer**. If it says "not sure", click **Wearing → No layer**, then vote cold again. |
| The camera doesn't accept the jacket | Zip it fully and sit back. If it still doesn't, turn the knob **right → DO → press**; that's also a valid answer. |
| The camera turns itself off (eye-off face) | Dashboard **Camera → On**. Keep the jacket away from the lens. |
| A suggestion shows "Take off a layer" | You were predicted warm. Take the jacket off, wait 30 s, start shot 4 again. |
| Temperature shows "–" | Run `tools/deploy_board.sh` on the laptop, wait 1 minute, and start over. |
| Room tab shows no "Set heating to…" | Click **Show** coworkers. The desk needs to be "present" (sit in view). |

---

## After recording (10 min)

1. Trim the start and end. Optionally add two captions: **"Coworkers: SIMULATED"** during shot 8, and **"Follow-up timer sped up for the demo"** during shot 5.
2. Upload to **YouTube as Unlisted**, titled *"Personal Weather: edge AI desk companion on Arduino UNO Q (Junction 2026)"*.
3. Put the link in `README.md` (top), `docs/junction-description.md` and `docs/project-hub.md`.
