# Personal Weather: Implementation Plan (v5)

Junction 2026 · Tuan Anh (software) and Minh (hardware) · Saturday 08:00 to Sunday 10:00 · Based on spec v5

## Key deadlines

| When | What |
|---|---|
| Friday 23:59 | Preliminary submission (draft + challenges selected) |
| Saturday 12:00 | Final submissions open |
| **Sunday 10:00** | **Final submission deadline**: repo, video, description, Arduino Project Hub page |
| Sunday 14:00 | Review (judging) |

About **26 hours** from Saturday 08:00. Plan for **~21 working hours each** with 4 hours of sleep.

---

## Roles

| | **Tuan Anh (software)** | **Minh (hardware)** |
|---|---|---|
| Owns | All Python logic, the device's local API, the hub and dashboard, evaluation, write-ups | App Lab setup, Modulinos, microcontroller sketch, Bridge, camera pipeline, clothing dataset and classifier, enclosure, Project Hub materials, video |
| Spec functions | C3, C6, C7, C8, C9, A1–A4 | C1, C2, C4, C5 |
| Develops on | Laptop first, against mocks; then deploys to the board | The board directly |
| Load | ~21 h | ~21 h |

**Why this works:** Tuan Anh never waits for hardware, because he builds against mock sensor, knob and vision inputs. Minh never waits for logic, because his parts are tested with simple test scripts. You meet at fixed integration points.

---

## 0. Kickoff contract (Saturday 08:00–08:45, together)

Agree on these before splitting up; write them into `docs/interfaces.md`.

### 0.1 Repo layout
```
personal-weather/
  device/
    sketch/            (Minh) microcontroller: Modulinos, LED face, buzzer, knob
    python/            Linux side of the UNO Q
      main.py          (Tuan Anh) main loop
      bridge_io.py     (Minh) talks to the sketch
      vision.py        (Minh) camera -> presence, clothing, camera status
      comfort.py       (Tuan Anh) PMV baseline, 3 classes, personal offset
      suggest.py       (Tuan Anh) mode-aware suggestions, responses, Beta experience
      api.py           (Tuan Anh) device local API for the dashboard
      summary.py       (Tuan Anh) minimal summary -> hub
  hub/                 (Tuan Anh) laptop: server + dashboard + room add-ons
  tools/
    mocks.py           (Tuan Anh) fake sensors/knob/vision
    face_test.py       (Minh) cycles all LED/buzzer states
    eval/              classifier (Minh) and model (Tuan Anh) evaluation
  docs/                interfaces, results, README material
```

### 0.2 Message contracts

| Direction | Message |
|---|---|
| Sketch → Linux (1 Hz) | `{"t": 23.4, "rh": 41.2}` |
| Sketch → Linux (knob) | `{"knob": "turn", "pos": -1}` (−1, 0, +1) · `{"knob": "press"}` |
| Linux → Sketch | `{"face": "smile"}` (smile, sun, snow, suggest_layer_on, suggest_layer_off, feedback + pos, check, text, eye_off, off) · `{"face": "text", "text": "DO"}` · `{"beep": "chirp"}` (chirp, chime, low) |
| vision.py → main.py | `{"present": true, "clothing": "outer", "conf": 0.86, "camera": "on"}` (clothing: outer, none, uncertain; camera: on, off, shutter) |
| Dashboard → device API | `POST /control` with `profile`, `camera`, `mode` (heating, cooling, unknown), `reset_pid`; `GET /state` for the dashboard (local only, labelled debug) |
| Device → hub (spec C8) | `{"pid": "p-7f3a", "present": true, "mode": "heating", "band_now": [21.0, 22.5], "band_with_fix": [19.5, 22.5], "state": -1, "unresolved": false}` |

### 0.3 Agreements
- One Git repo; separate folders; merge often.
- Laptop runs a **Wi-Fi hotspot**; the UNO Q joins it with a fixed address or `.local` name.
- Blocked for more than 30 minutes → say so immediately.
- **Real vs simulated:** anything simulated or accelerated is labelled in the UI from the start.

---

## 1. Timeline

### Block 1 · Saturday 08:45–11:00 · Foundations

| Tuan Anh (software) | Minh (hardware) |
|---|---|
| **T1.1** Repo; `tools/mocks.py` (temperature curve, scripted knob, fake vision) | **M1.1** App Lab running; board on the hotspot; hello-world app |
| **T1.2** `comfort.py`: PMV baseline with the declared assumed inputs; try `pythermalcomfort`, fall back to a hand-written ISO 7730 function if it won't install on the board | **M1.2** Thermo, Knob, Buzzer wired; sketch reads them; Thermo outside the case |
| **T1.3** 3-class mapping (±0.5) and the **personal offset** | **M1.3** Knob: turn position + press (nothing more) |
| **T1.4** Test installs on the board (numpy, PMV code, web server library) | **M1.4** Camera capture in Python; time the smallest person detector |
| | **M1.5** Clothing dataset session 1 (both of you + consenting volunteers; empty chair) |

**Sync 11:00 (15 min):** sensors and knob read on the board; detector speed known; comfort code installs on the board.

### Block 2 · Saturday 11:00–14:00 · Core logic and the vision gate

| Tuan Anh (software) | Minh (hardware) |
|---|---|
| **T2.1** `suggest.py`: mode-aware suggestion engine (spec section 2); responses **Do it / Not possible / Not now**; 15-min limit | **M2.1** LED face: comfort icons, suggestion icons, DO/NO/LATER text, feedback arrows, check, eye-off; buzzer; `face_test.py` |
| **T2.2** Follow-up + Beta experience: update only after "Do it" + an actual follow-up response; missing = unknown; "Not possible" never updates | **M2.2** `bridge_io.py` per the contract |
| **T2.3** Prospective evaluation: before each update, log baseline and personal predictions as classes; 3-class accuracy and MAE on −1/0/+1 | **M2.3** Dataset sessions 2–3; train in Edge Impulse; hold out a whole session |
| **T2.4** `main.py` state machine with mocks; two profiles | **M2.4** Deploy classifier; torso crop; stability; `uncertain`; **dark-frame detection → camera status "shutter"** |

**14:00 GATE (Minh, with Tuan Anh):** [ ] runs on the UNO Q with acceptable latency · [ ] reliable on both of you · [ ] held-out-session result written down · [ ] `uncertain` fallback works.
**Pass:** Minh continues vision polish. **Fail:** clothing is set on the dashboard; Minh stops vision and moves to enclosure, recorded cold episode and video.

### Block 3 · Saturday 14:00–17:00 · First integration on the device

| Tuan Anh (software) | Minh (hardware) |
|---|---|
| **T3.1** Deploy `main.py`, `comfort.py`, `suggest.py` to the board; swap mocks for `bridge_io.py` and `vision.py` | **M3.1** `vision.py` per the contract, including camera off (process stops) and shutter detection |
| **T3.2** `api.py`: `/state` and `/control` (profile, camera, mode, pseudonym reset) | **M3.2** Help with on-board integration: messages, timing, crashes |
| **T3.3** `summary.py`: persistent pseudonym, `band_now`, `band_with_fix`, `unresolved`; send once a minute and on change | **M3.3** Enclosure v1 (cardboard): camera with physical shutter, LED and knob on the front, Thermo outside |

**INTEGRATION 1 · 17:00 (30 min, together):** real readings → real feedback → clothing recognised → "Add a layer?" → Do it → layer on → camera confirms → follow-up → offset and Beta update; shutter closed → camera status "shutter".
**If not working by 17:30, both work on it until it is.**

### Block 4 · Saturday 17:30–21:00 · Dashboard and room level

| Tuan Anh (software) | Minh (hardware) |
|---|---|
| **T4.1** Dashboard v1: people cards, evidence panel, fix experience with uncertainty, privacy receipt (actual data flow), controls | **M4.1** Vision polish (if gate passed): more sessions; held-out-person test; results in `docs/results.md` |
| **T4.2** Hub: receive summaries; receipt-time handling; stale after 2 min | **M4.2** Robustness: app auto-starts; reconnects to the hotspot |
| **T4.3** **A1** room recommendation (heating: lowest setpoint where everyone is OK with feasible fixes; cooling: highest; unknown: none) with **Agree** button | **M4.3** **Record a genuine cold episode** (e.g. near the entrance) with real feedback, for the demo backup |
| **T4.4** **A2** simulated coworkers, visually labelled "SIMULATED" | **M4.4** Device photos; demo props (jacket, hoodie, printed label) |

**INTEGRATION 2 · 21:00 (30 min):** full demo run #1 (all 7 steps). Write down every problem.

### Block 5 · Saturday 21:30–02:00 · Fix, finish add-ons, write

| Tuan Anh (software) | Minh (hardware) |
|---|---|
| **T5.1** Fix problems from run #1 | **M5.1** Fix device problems from run #1 |
| **T5.2** **A3** unresolved discomfort bars (no single score); weighting in A1 | **M5.2** Enclosure v2 (3D print if the queue allows) |
| **T5.3** **A4** energy panel: Measured / Proposed / Modelled, each labelled | **M5.3** Project Hub material: wiring diagram, parts list, build steps |
| **T5.4** README: data flow and privacy limits, evaluation method and results, assumptions; Junction description | **M5.4** Architecture diagram; classifier results write-up |

**01:30:** full demo run #2, then **freeze core features**. Stretch (only if both runs passed): X1 residual model (Tuan Anh).
**02:00–06:00:** sleep. Leave the device logging overnight for a real-data chart.

### Block 6 · Sunday 06:00–10:00 · Submit

| Time | Tuan Anh | Minh |
|---|---|---|
| 06:00–07:30 | Bug fixes only; dashboard polish | Record the ~2-minute demo video (Tuan Anh on camera) |
| 07:30–08:30 | Finalise README + Junction description; push repo | Edit video; publish Arduino Project Hub page (*Junction Finland 2026*) |
| 08:30–09:30 | Submit on Junction (main challenge + Best use of Arduino UNO Q) | Check every link from another device |
| **09:30** | **Submitted, 30 minutes before the deadline** | |

### Sunday 10:00–14:00 · Rehearse
- At least **3 timed run-throughs** of the 3-minute demo.
- Prepared answers:
  - *Does it save energy?* Only through the mode logic: in heating, a layer replaces a request for more heat, and warm people show the heating could be lowered. Proposed changes need agreement; HVAC effects are modelled, not measured.
  - *What does it control?* Nothing automatically. It offers optional suggestions and a room proposal that a person agrees to.
  - *How accurate is the classifier?* Held-out-session (and held-out-person) results.
  - *Is the personal model better?* Prospective 3-class accuracy and MAE vs the baseline, with the sample count.
  - *What leaves the desk?* Show the privacy receipt.
- Keep the dashboard clothing fallback ready in case vision fails on stage.

---

## 2. Workload balance

| Block | Tuan Anh | Minh |
|---|---|---|
| Kickoff | 0.75 | 0.75 |
| Block 1 | 2.25 | 2.25 |
| Block 2 | 3 | 3 |
| Block 3 | 3 | 3 |
| Block 4 | 3.5 | 3.5 |
| Block 5 | 4.5 | 4.5 |
| Block 6 | 4 | 4 |
| **Total** | **~21 h** | **~21 h** |

---

## 3. Core-first checklist

**By Integration 1 (17:00)**
- [ ] C1 sensing on the board (Minh)
- [ ] C4 knob turn + press (Minh)
- [ ] C5 LED face + buzzer (Minh)
- [ ] C2 presence + clothing, or dashboard fallback; shutter detection (Minh)
- [ ] C3 baseline + 3 classes + personal offset + prospective evaluation (Tuan Anh)
- [ ] C6 mode-aware suggestions with three responses (Tuan Anh)
- [ ] C7 follow-up + Beta experience (Tuan Anh)
- [ ] Two profiles (Tuan Anh)

**By Integration 2 (21:00)**
- [ ] C8 summary + privacy receipt (Tuan Anh)
- [ ] C9 dashboard with controls (Tuan Anh)
- [ ] A1 room recommendation with Agree (Tuan Anh)
- [ ] A2 labelled simulated coworkers (Tuan Anh)
- [ ] Recorded genuine cold episode (Minh)

**By 01:30**
- [ ] A3 unresolved discomfort (Tuan Anh)
- [ ] A4 three-layer energy panel (Tuan Anh)
- [ ] Enclosure v2, Project Hub material (Minh)

**Only after that:** stretch items (spec section 7).

---

## 4. Fallbacks

| If… | Then… |
|---|---|
| `pythermalcomfort` won't install on the board | Hand-written PMV function |
| Person detector too slow | Lower resolution / rate; or presence from knob activity |
| Clothing gate fails at 14:00 | Clothing set on the dashboard; Minh moves to enclosure, cold episode, video |
| Personal offset isn't better than the baseline | Report it honestly in the evidence panel |
| Board-to-hub networking fails | Run the hub on the board; open the dashboard from the laptop |
| Venue too warm for a genuine cold report | Warm branch live; recorded real cold episode, labelled |
| Integration 1 slips past 17:30 | Both on it; postpone Block 4 room add-ons |
| Running late on Sunday | Submit at 09:30 with what works; never miss 10:00 |

---

## 5. Tonight (Friday)
- [ ] Preliminary submission before 23:59
- [ ] Git repo created, both added
- [ ] Arduino App Lab installed on both laptops
- [ ] Edge Impulse account (Minh)
- [ ] Bring a jacket, a hoodie, chargers
