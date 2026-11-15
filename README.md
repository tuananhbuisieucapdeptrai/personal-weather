# Personal Weather

> *The cheapest kilowatt-hour is a jacket.*

**A privacy-first Edge AI desk companion on the Arduino UNO Q.**
- It learns how *each* person experiences the same room.
- It offers optional free comfort fixes, such as putting on a layer, before anyone asks for more heating.
- It helps a shared office agree on a heating or cooling setpoint that needs less energy.
- Camera images never leave the desk.

Junction 2026 · Challenge: **Make Europe Green through Edge AI using Arduino** (and Best use of Arduino UNO Q)
Team: Tuan Anh (software) · Minh (hardware)

**Links:**
- Repo: https://github.com/tuananhbuisieucapdeptrai/personal-weather
- Demo video: https://youtu.be/vJDm6AkoRAI
- Slides: [docs/personal-weather-slides.pdf](docs/personal-weather-slides.pdf)
- Arduino Project Hub: ⏳

> Items marked **⏳ TO FILL** are measurements we haven't made yet. We would rather leave a gap than invent a number.

---

## What it does

| | |
|---|---|
| **Personal** | Two people in the same room get different predictions and different advice. A small personal offset, learned from their own feedback, corrects a standard comfort formula. |
| **Perceptive** | The camera on the desk detects presence and whether you're wearing an outer layer. A small on-device model does this, and images are processed in memory only. |
| **Adaptive** | After a person accepts a fix, the device asks whether it helped and keeps an honest per-person record of what works ("4 helped, 1 didn't → about 71 %, high uncertainty"). |
| **Mode-aware energy logic** | In **heating** season, a layer replaces a request for more heat, and warm people are evidence that the heating could be lowered. **Cooling** mirrors this. When the season is **unknown**, it gives comfort advice only and makes no energy claims. |
| **Humans decide** | Suggestions are optional ("Do it / Not now / Not possible", with no penalty). Room setpoint changes need someone to click **Agree**, and the thermostat is changed by hand. |
| **Discomfort stays visible** | People who stay uncomfortable with no free fix appear as a bar that doesn't disappear, and they weigh more in the room recommendation. |

**Works automatically.**
- Comfort is predicted from measured temperature and humidity plus the clothing the camera sees.
- The knob is an **optional** one-click correction ("I'm cold") that takes effect at once and personalises the model over time.
- Putting on the suggested layer counts as accepting the suggestion; no button needed.

**Deliberately no emotion recognition.**
- The camera only checks *presence* and *outer layer vs none*.
- Inferring emotions of people at work is prohibited by the EU AI Act (Art. 5(1)(f)), and facial expression is weak evidence of thermal comfort anyway.

## How it works

```
 Desk (Arduino UNO Q)                                                Laptop (hub)
 ┌──────────────────────────────────────────────────────────┐        ┌──────────────────────────┐
 │ Microcontroller (sketch)          Linux side (Python)    │        │ hub/server.py            │
 │  Modulino Thermo ── t, rh 1 Hz ─▶ smoothing (sensing)    │        │  receives summaries,     │
 │  Modulino Knob   ── turn/press ─▶ comfort (PMV+offset)   │ C8     │  stale after 2 min       │
 │  LED matrix face ◀── faces ───── suggestions, follow-up  │summary │  room view: A1–A4        │
 │  Modulino Buzzer ◀── beeps ────── evaluation log         │──────▶ │  dashboard page          │
 │                    (App Lab Bridge)                      │ 1/min  └──────────────────────────┘
 │  USB camera ─▶ vision (presence; clothing → fallback)    │ + on change
 │               frames in memory only; shutter → stop      │
 │  device API :8000 (GET /state, POST /control)            │
 └──────────────────────────────────────────────────────────┘
```

1. **Sense:** temperature and humidity once per second, smoothed in Python (raw values kept).
2. **Predict:** a PMV comfort estimate (ISO 7730) plus a per-person offset, giving one of three classes: cold, OK or warm.
3. **Suggest:** if a free fix is predicted to make the person OK, the LED face shows it and the knob answers it. At most one suggestion every 15 minutes.
4. **Learn:** after "Do it", the device waits, checks the clothing change, and asks "did it help?". The answer updates the offset and the fix record.
5. **Share minimally:** once a minute, and whenever something changes, each desk sends a pseudonymous summary to the hub. The hub recommends a room setpoint, which a person agrees to or not.

## Hardware

Arduino UNO Q (2 GB) · Modulino Thermo (mounted outside the case) · Modulino Knob · Modulino Buzzer · onboard LED matrix · USB camera with a **physical shutter** · a laptop as the hub. Enclosure: ⏳ TO FILL (Minh).

## Repository

```
device/            App Lab app that runs on the UNO Q
  sketch/          microcontroller: Modulinos, LED faces (faces.h), knob, buzzer
  python/          Linux side: main.py, app.py, comfort.py, suggest.py, evaluation.py,
                   sensing.py, vision.py, shutter.py, bridge_io.py, api.py, summary.py,
                   contracts.py (all message shapes, checked)
hub/               laptop: server.py, room.py (A1–A4), static/index.html (desk), static/room.html (room)
tools/             mocks.py (fake board), tests/, eval/, kickoff/, net/
docs/              spec, plan, interfaces, hardware and board results
```

## Run it

**On a laptop, without the board** (Python 3.9+, standard library only):

```bash
python3 hub/server.py --demo
```
```bash
PW_HUB_URL=http://127.0.0.1:8080 python3 device/python/main.py --mock --demo
```

- Desk view: `http://127.0.0.1:8080/?device=http://127.0.0.1:8000`
- Room view: `http://127.0.0.1:8080/room`
- Type `+`, `0`, `-` and `p` in the mock terminal to turn and press the knob.
- Mock data is labelled "Demo data", and sped-up timers are labelled "Sped up".

**On the UNO Q:**
1. In App Lab, create or import an app from `device/`. `app.yaml` publishes port 8000.
2. Set `RUN_BOARD_CHECK = False` in `device/python/main.py`. `True` runs the hardware self-check instead.
3. Tell the board where the hub is. In the app's `python/` folder on the board, run:
   ```bash
   python3 summary.py --set-hub http://<laptop-ip>:8080
   ```
4. On the laptop, run `python3 hub/server.py`, then open `http://<laptop-ip>:8080/?device=http://pw-desk.local:8000`.

Only one App Lab app can use the camera and port 8000 at a time.

**Tests:**

```bash
python3 -m unittest discover -s tools/tests
```

Each module also has a self-test, e.g. `python3 device/python/comfort.py`.

## Data flow and privacy

| Data | Where it lives | Leaves the desk? |
|---|---|---|
| Camera frames | In memory, in a separate process | **Never.** Not stored, not sent. |
| Feedback votes and the prospective evaluation log | `state/feedback_log.jsonl` on the device | No |
| Personal offset, suggestion history, fix record | `state/profiles.json` on the device | No |
| Pseudonym per profile (`p-xxxx`) | `state/pids.json` on the device | Only as the ID in the summary |
| **Summary** (spec C8) | Sent to the hub once a minute and on change | **Yes, exactly this:** |

```json
{ "pid": "p-7f3a", "present": true, "mode": "heating",
  "band_now": [21.0, 22.5], "band_with_fix": [19.5, 22.5],
  "state": -1, "unresolved": false }
```

- The hub stamps the **receipt time** and ignores device clocks. A summary older than 2 minutes counts as absent.
- The room view uses **only** these summaries: no names, votes or images.
- The desk dashboard shows the exact message sent, as a **privacy receipt**.

**Privacy limits (stated honestly):**
- **Pseudonyms persist on purpose.** The hub needs continuity to show unresolved discomfort over time. A person can reset theirs from the dashboard.
- **The hub sees the device's local network address.**
- **The device API is unauthenticated and meant for a trusted local network only.** It is labelled "local · debug". Anyone on the same network could read the desk view or change its settings. A shared token is future work.
- **Camera off is enforced twice:**
  - The **physical shutter** is the real guarantee. After about 3 s of dark frames, the software releases the camera and reports `shutter`. The darkness threshold is 20/255: a closed shutter reads 0.7, the room ~145. It was lowered from 72 after a dark jacket close to the lens falsely triggered it.
  - Capture resumes only after an explicit "camera on".
  - It doesn't watch for the shutter reopening, because that would require capturing frames while it's closed.
- **Training images** for the clothing classifier are collected only in a separate session, from people who consented, and are deleted after the event. They are never in this repository (`.gitignore` blocks images).

## Evaluation

### Comfort model: does the personal offset beat the baseline?

**Method (declared before collecting data):**
- On every feedback vote (−1 cold, 0 OK, +1 warm), and **before** updating, the device logs the class predicted by the baseline and by the personal model.
- We report prospective 3-class accuracy and mean absolute error on the −1/0/+1 scale, with the sample count.
- With fewer than 5 votes we say "too few samples". If the personal model isn't better, we say so.
- Mock and simulated votes are labelled and kept out of LIVE results.

**Simulated sanity check** (labelled SIMULATED, not evidence about real people). Synthetic people with a hidden true offset, vote noise sd 0.35 PMV, 200 runs × 15 votes each (`tools/eval/sim_offset.py`):

| Synthetic person | Baseline accuracy | Personal accuracy | Baseline MAE | Personal MAE |
|---|---|---|---|---|
| runs cold (−0.7) | 0.48 | **0.73** | 0.54 | **0.27** |
| average (0.0) | **0.75** | 0.73 | **0.25** | 0.27 |
| runs warm (+0.6) | 0.46 | **0.66** | 0.54 | **0.34** |

The offset helps people who differ from the average a lot. It costs a little for an average person, because noisy votes nudge the offset around.

**Live results (real feedback on the device):**
- **Not enough genuine votes yet.** Tonight's votes were knob tests and debugging, deliberately clicking cold, OK and warm within minutes, so they say nothing about real comfort.
- We archived them on the device (`*.test-2026-11-14`) instead of counting them, and started a fresh log.
- The table fills in once each person has given genuine votes over days. Generate it with:

```bash
python3 tools/eval/live_report.py --log <copy of state/feedback_log.jsonl>
```

| Person | Votes | Baseline accuracy | Personal accuracy | Baseline MAE | Personal MAE | Verdict | Data |
|---|---|---|---|---|---|---|---|
| ⏳ | | | | | | | |

### Baseline correctness

- The hand-written ISO 7730 PMV matches the standard's published examples (6 rows, within 0.02).
- It agrees with `pythermalcomfort` to within **0.0009 PMV over 522 office conditions**, with no class differences (`tools/eval/check_pmv.py`).
- We didn't run `pythermalcomfort` on the board, because it pulls in about 300 MB of dependencies.

### Vision (Minh)

- **Presence:** a frontal-face cue with a HOG fallback, filtered over 3 observations. Board acceptance passed in the tested setup: leaving gave absent, returning gave present, and shutter / restart behaved correctly. Inference time: mean **264 ms**, max **454 ms** over 150 inferences. This isn't a quantitative accuracy evaluation.
- **Clothing, what we tried and what we use:**
  - **Trained model (Minh):** MobileNetV3-Small with a two-class head, trained on 240 consented desk photos of both of us.
    - Offline holdout: **37/40 = 92.5 %**, reproduced on the UNO Q.
    - **It failed a live test:** it was consistently *inverted* for one person (confident "outer" with no jacket, "none" with a jacket). It most likely learned colour and sleeve shortcuts from too little, too uniform data. **Not used.**
  - **Used: zero-shot CLIP** (OpenAI ViT-B/32, image half only, 8-bit ONNX, 88 MB).
    - The image is compared with fixed text descriptions ("a person wearing a jacket / coat / hoodie…" vs "…a t-shirt / shirt…"). It is **never trained on our photos**, so it can't learn their shortcuts.
    - The "outer" cut-off was chosen on 257 desk photos, then checked once on the separate 40-photo holdout.

    | Test | Outer layer found | No layer correct |
    |---|---|---|
    | Calibration (257 photos) | 129/137 | 119/120 (96.5 % overall) |
    | **Holdout (40 separate photos)** | **20/20** | **20/20** |

    - Speed on the UNO Q: **~540 ms** per classification, run every 1.5 s. A label changes only after 2 agreeing results.
    - **Live test:** no jacket → "no layer" ✅. Zipped jacket → "outer layer" ✅. **Open jacket over a T-shirt → mostly "no layer" ❌**: with a chest-framed camera the T-shirt dominates the image.
  - **Presence:** the camera faces the chest, so faces are rarely visible. Presence is **small movement or a frontal face**, held for 60 s, at ~2–60 ms per frame. It was stable in a 20-second seated test.
- The dashboard's manual "Wearing" setting remains as a fallback.

### On the device

- `env_check.py` passes **20/20 inside the App Lab container** (Python 3.13). Nothing needs installing.
- One full comfort estimate, including the comfort band, takes **3.1 ms** on the UNO Q.
- Board bring-up: Thermo, Knob and Buzzer detected; 1 Hz readings with decimals; 17/17 Bridge commands acknowledged; all 13 knob checks passed (`docs/kickoff-board-results.md`).

### Automated tests

23 unit and end-to-end tests run with mocks (app, room, Bridge, vision), plus a self-test in every module.

Known issue: one vision lifecycle test (`test_stop_idempotence_and_restart`) occasionally times out when the machine is under load.

## Assumptions

- **Comfort formula:** PMV (ISO 7730) from **measured** air temperature and humidity. The other inputs are **assumed**:
  - radiant temperature = air temperature
  - air speed 0.1 m/s
  - activity 1.2 met (sedentary office work)
  - clothing: 1.0 clo with an outer layer, 0.6 clo without; 0.8 clo when unknown, flagged as assumed
- **Classes:** PMV < −0.5 is cold, −0.5…+0.5 is OK, > +0.5 is warm.
- **Personal offset:**
  - Each vote pulls the prediction toward the vote's zone. The step is 1/(n+2), never below 0.15, and the offset is clipped to ±2.
  - A vote that already agrees with the prediction changes nothing.
- **Comfort band:** air temperatures where the personal prediction is OK, at the current humidity and clothing. `band_with_fix` is the band with the season's energy-relevant fix: a layer in heating, no layer in cooling.
- **Suggestions:**
  - At most one per 15 min, and a response is needed within 2 min.
  - "Not possible" blocks that fix for 4 h, with no penalty.
  - The follow-up comes after 5 min (30 s in the demo, labelled).
- **Fix record:** Beta(1,1) prior per person and fix. It shows **association, not causation**.
- **Room recommendation:**
  - Candidate setpoints from 18 to 27 °C in 0.5 °C steps.
  - Heating takes the lowest setpoint that suits everyone present, cooling the highest. A fix counts only if it's feasible.
  - Changes under 0.5 °C aren't proposed. After an agreement, the next proposal waits 90 min, unless people arrive or leave, or someone has been unresolved for 20+ min.
  - In the fallback, weights are 1 + unresolved minutes / 30, at most 3.
- **Not modelled:** sun load, drafts, the radiator, and air speed changes.

## Energy claims

Energy is shown in three separate layers. No percentage is claimed for this device.

| Layer | What it shows |
|---|---|
| **Measured** | What the hub actually saw: people present, comfortable, with a free fix, with no fix |
| **Proposed** | The recommended setpoint, which needs agreement. The thermostat itself isn't verified. |
| **Modelled** | Research context only. Building simulations suggest wider acceptable setpoint ranges can reduce HVAC energy, with the size depending on climate and building: Hoyt, Arens & Zhang (2015), *Building and Environment* 88:89–96, doi:10.1016/j.buildenv.2014.09.010 |

## Compared with existing solutions

| Kind of product | Examples | What it does | Where Personal Weather differs |
|---|---|---|---|
| Smart thermostats | Google Nest, ecobee (with room sensors) | Learn schedules and occupancy, adjust the HVAC | They optimise the **building's** temperature; we predict **each person's** comfort, including what they wear |
| Occupant comfort apps | Comfy (Siemens) and similar "warmer / cooler" apps | People report discomfort; the building system changes the zone | They answer discomfort **with HVAC energy**; we offer a **free fix first**, and work with an **ordinary thermostat**, with no building-system integration |
| Personal comfort devices | Desk fans and heaters, heated chairs, wearables | Change one person's micro-climate | They use energy or must be worn, and don't help a room agree on a setpoint |
| Research | UC Berkeley CBE personal comfort models | Per-person comfort prediction | We run it on a low-cost edge device, with on-device vision and a closed suggest → act → check loop |

**What's distinctive:**
- a free fix before energy, with season-aware energy logic;
- a personal, adaptive model that also checks whether fixes helped;
- vision on the device, with only an anonymous summary leaving the desk and a physical shutter;
- no cloud;
- unresolved discomfort stays visible;
- honest three-layer energy claims.

## Limitations and next steps

- Clothing detection is validated on a small two-person photo set plus short live tests. It misses open jackets. The manual "Wearing" fallback stays.
- No genuine live comfort-model results yet (only test votes from one evening, archived).
- No authentication on the device API.
- Simulated coworkers stand in for a real multi-desk office. They are always labelled SIMULATED.
- One air sensor per desk: drafts, sun and radiators aren't measured. Only two fixes so far (add or remove a layer).
- Future work:
  - opt-in, on-device **posture cues** of thermal discomfort (arms crossed, rubbing hands), never emotions
  - a larger fix menu (move away from the window, close the blinds) with extra sensors
  - a multi-room / **smart-building view**
  - a multi-feature personal model (X1), kept only if it beats the offset prospectively
  - several real desks
  - thermostat integration, still with human agreement

## Credits

- Comfort model: ISO 7730 (Fanger PMV), cross-checked against [`pythermalcomfort`](https://pythermalcomfort.readthedocs.io/).
- Research context: [CBE Personal Comfort Systems](https://cbe.berkeley.edu/research/personal-comfort-system/), and Hoyt, Arens & Zhang (2015).
- Presence detection: OpenCV cascade and HOG detectors.
- Built with Arduino App Lab, the UNO Q and Modulino.
