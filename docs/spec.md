# Personal Weather: Product Specification (v5)

> *The cheapest kilowatt-hour is a jacket.*

**Subtitle:** Edge AI for personal comfort and fairer rooms
**Event:** Junction 2026, European Tech Renaissance
**Main challenge:** The Green European Renaissance (Arduino)
**Tech challenge:** Best use of Arduino UNO Q (same build)
**Team:** Tuan Anh (software), Minh (hardware)
**Hardware:** the Arduino kit only

**What changed from v4** (after Astra's review): heating / cooling / unknown operating mode, so energy logic runs in the right direction; suggestions are explicitly optional with three different responses; the personal offset is core and the multi-feature model is an add-on; a defined evaluation metric; knob reduced to turn + confirm; several data-flow contradictions fixed; fairness rescoped to visible unresolved discomfort; energy shown in three clearly separated layers; no score predictions. Earlier versions: `personal-weather-spec-v1.md` to `-v4.md`.

---

## 1. Overview

**One-liner:** Personal Weather is a privacy-first Edge AI desk companion that learns how each person experiences the same room, offers optional free comfort fixes, and helps a shared room agree on a heating or cooling setting that needs less energy, without sending images off the desk.

**What it does better than a thermometer and a generic reminder:**
1. **Personal:** two people in the same conditions get different predictions and different advice.
2. **Perceptive:** it recognises clothing on the device, so advice fits what the person is actually wearing.
3. **Adaptive:** it learns, from follow-up feedback, which fixes tend to work for each person.

### Principles
1. **Energy logic follows the operating mode.** In heating season, a free fix matters when it stops someone asking for *more heat*. In cooling season, when it stops someone asking for *more cooling*. When the mode is unknown, the device gives comfort advice only and makes no energy claims.
2. **Suggestions are optional.** Declining or being unable to act never counts against a person.
3. **Humans decide room changes.** The room recommendation needs agreement from the person responsible for the thermostat.
4. **Persistent discomfort stays visible.** Optimisation never hides someone who stays uncomfortable.
5. **Claims match evidence.** Measured, proposed and modelled numbers are always labelled separately.

### Intended setting
A shared office room with an **ordinary wall thermostat** (or radiator valves) that is accessible, and **an agreed person responsible** for adjusting it. That's where personal fixes can actually change the room setting.

---

## 2. Operating modes and energy logic

The mode is set on the dashboard (default for Finland in November: **heating**).

| Mode | Cold person | Warm person | Energy effect |
|---|---|---|---|
| **Heating** | Suggest **adding a layer** instead of requesting more heat | Evidence the room **may be overheated**: contributes to a "could lower the heating" recommendation. Removing a layer is offered as comfort advice only, never counted as saving | Lower or unchanged heating setpoint |
| **Cooling** | Evidence the room **may be over-cooled**: contributes to a "could raise the cooling setpoint" recommendation | Suggest **removing a layer** (or other free fix) instead of requesting more cooling | Higher or unchanged cooling setpoint |
| **Unknown** | Comfort advice only | Comfort advice only | **None claimed** |

**Key correction from earlier versions:** taking off a jacket in an overheated room saves no energy; it can hide excessive heating. In heating mode the right response to a warm person is to consider lowering the heating.

---

## 3. Hardware (Arduino kit only)

| Component | Role |
|---|---|
| **Arduino UNO Q** (2 GB) | Linux side: person and clothing recognition, comfort estimate, suggestions, learning, local API. Microcontroller: Thermo, knob, LED face, buzzer |
| **USB Camera** (via USB-C hub) | Presence and clothing state, on the device only |
| **Modulino Thermo** | Temperature and humidity (mounted outside the case, away from board heat) |
| **Modulino Knob** | Turn + confirm only |
| **Modulino Buzzer** | Rare sounds |
| **Onboard LED matrix** | The weather face |
| **Laptop** | Room Hub and dashboard; Wi-Fi hotspot |

**Enclosure:** cardboard or quick 3D print; camera on top with a **physical shutter**; LED and knob on the front.

---

## 4. Tiers

| Tier | Contents |
|---|---|
| **Core** | C1–C9: one genuine adaptive personal loop on the device, with its privacy receipt |
| **Add-ons** | A1–A4: the room level (heating/cooling-aware recommendation, labelled simulated coworkers, unresolved discomfort, energy layers) |
| **Stretch** | X1–X6 |

---

## 5. Core

### C1. Environment sensing
Temperature and humidity once per second, smoothed; sent over the App Lab Bridge. **Done when:** live values on the dashboard.

### C2. Presence and clothing recognition (on device)
- **Outputs only:** `present` / `absent`; `outer_layer` / `no_outer_layer` / `uncertain`.
- **How:** person detection about once per second at low resolution → torso crop → small clothing classifier every few seconds; a state is accepted only after several consistent frames; low confidence → `uncertain` → clothing asked on the dashboard or defaults to unknown.
- **Physical shutter detection:** if frames are almost completely dark for a few seconds, the device **switches to camera-off automatically** and reports it. The shutter is the physical guarantee; the software state is reported separately and honestly.
- **Camera-off** can also be switched on the dashboard; the camera process then stops.
- **Training data:** both team members plus volunteers **who explicitly consent**; several separate sessions; varied clothing, backgrounds, lighting; empty-chair negatives; photos deleted after the event.
- **Evaluation:** hold out whole sessions (never neighbouring frames); held-out person if possible.
- **Gate Saturday 14:00:** running on the board with acceptable latency, reliable on both team members, held-out-session result recorded, `uncertain` fallback working. If not: clothing comes from the dashboard and vision work stops.

### C3. Comfort estimate and personal offset
- **Baseline:** *"an approximate comfort estimate using measured conditions and explicitly assumed inputs"*: PMV (ISO 7730) with measured temperature and humidity; **assumed** radiant temperature = air temperature, still air, seated activity; clothing approximated from `outer_layer` (e.g. 1.0 clo) / `no_outer_layer` (e.g. 0.6 clo).
- **Three classes:** baseline value below −0.5 → cold; −0.5 to +0.5 → OK; above +0.5 → warm.
- **Personal offset (core):** a single per-person bias added to the baseline, updated after each feedback.
- **Comfort band:** temperatures where the person's offset-corrected prediction is OK, adjusted as feedback arrives.
- **Evaluation metric (declared):** on each new feedback (−1 cold, 0 OK, +1 warm), **before updating**, record the prediction of both the baseline and the personal model, both as one of the three classes. Report **prospective 3-class accuracy** and **mean absolute error on the −1/0/+1 scale**, plus the sample count. If the personal model isn't better, say so.
- **Done when:** the evidence panel shows predictions, prospective errors and sample counts for both people.

### C4. Knob: turn + confirm only
- **Turn:** cold / OK / warm (and, while a suggestion is shown, choose a response).
- **Press:** confirm.
- Profiles, camera-off and mode live on the **dashboard**.

### C5. Weather face
| State | LED | Buzzer |
|---|---|---|
| Comfort | smiley / sun / snowflake | — |
| Suggestion | fix icon blinking | one chime |
| Choosing a response | "DO" / "NO" / "LATER" scrolling as the knob turns | click |
| Feedback | arrow left / dot / arrow right; check mark on confirm | chirp on confirm |
| Camera off | crossed-out eye, then corner dot | low beep |

### C6. Suggestion engine (optional, mode-aware)
- Uses the comfort estimate with the clothing change applied to check whether a free fix would make the person OK; follows the mode table in section 2.
- **Three responses** (knob turn + press):
  - **"Do it"** → follow-up (C7).
  - **"Not possible for me"** → recorded as a constraint, **no penalty**; not suggested again in that context.
  - **"Not now"** → no penalty; may be suggested again later.
- At most one suggestion every 15 minutes.

### C7. Follow-up and fix experience
- After "Do it", the device waits a few minutes (shortened and labelled in the demo), checks whether the clothing change is visible (C2), then asks for feedback.
- **Updates only after an accepted action plus an actual follow-up response.** Missing feedback = unknown, not failure. "Not possible" never updates it.
- Per person and fix: Beta(1, 1) prior; OK after the action → success; still uncomfortable → failure.
- **Wording:** "context-dependent experience", e.g. "Adding a layer, for TA: 4 helped, 1 didn't → about 71%, high uncertainty". The camera shows the action was done; the feedback shows comfort afterwards; **neither proves the action caused the change.**

### C8. Minimal comfort summary and privacy receipt
**Summary sent to the hub:**
```json
{ "pid": "p-7f3a", "present": true, "mode": "heating",
  "band_now": [21.0, 22.5], "band_with_fix": [19.5, 22.5],
  "state": -1, "unresolved": false }
```
- `pid`: a **persistent pseudonymous ID** (random, not a name; the person can reset it on the dashboard). Chosen deliberately because the hub needs continuity for unresolved-discomfort history. Documented in the README.
- `band_with_fix`: the band if the person's feasible free fix were applied (omitted if they said "not possible").
- Sent at most once a minute and on change. The hub **uses receipt time**; a summary older than **2 minutes is stale** and the person is treated as absent.
- **Privacy receipt (dashboard), stating the actual data flow:**
  - sent: the last summary, exactly as above;
  - network metadata: the device's local network address is visible to the hub;
  - stored on the device: the person's feedback log and model values;
  - images: processed in memory, not stored or sent; camera status (on / off / shutter detected);
  - training images: collected only in a separate, consented session, and deleted after the event.

### C9. Local dashboard (laptop)
One page: people cards (current state, prediction, band, suggestion status), the evidence panel (C3), fix experience with uncertainty (C7), privacy receipt (C8), and controls: **profile switch, camera on/off, operating mode, pseudonym reset**.

---

## 6. Add-ons (the room level)

### A1. Heating/cooling-aware room recommendation (needs human agreement)
- For each candidate setpoint, evaluate **every present person's comfort at that setpoint**, using `band_with_fix` only where a fix is feasible. A person whose fix works now is **not** assumed to be fine at any setpoint.
- **Heating:** recommend the **lowest** setpoint where everyone is OK (with feasible fixes); **cooling:** the **highest**. **Unknown:** no recommendation.
- Cadence: a morning recommendation, re-check only on arrivals/departures or 20+ minutes of unresolved discomfort, at least 90 minutes apart, changes of 0.5 °C or more.
- Shown as a proposal with an **"Agree"** button for the person responsible; nothing changes without it.

### A2. Simulated coworkers (clearly labelled)
2–3 synthetic profiles so the room level can be demonstrated. **Visually distinct** from the real desk (label "SIMULATED"); accelerated time is labelled too.

### A3. Unresolved discomfort (replaces the fairness %)
- Per person: **minutes uncomfortable with no feasible fix** (including "not possible"), shown as a bar that stays visible.
- The room recommendation gives more weight to people with more unresolved minutes. **No single fairness score.**

### A4. Energy panel in three layers
| Layer | Example | Label |
|---|---|---|
| **Measured** | Comfort responses, accepted fixes | "Measured" |
| **Proposed** | "Recommended heating setpoint: 21.0 °C instead of 21.5 °C" | "Proposed (needs agreement)" |
| **Modelled** | Possible HVAC effect of the proposed change | "Modelled: research context, not a measured saving" |

Research context for the modelled layer: building simulations suggest that wider acceptable setpoint ranges can reduce HVAC energy, with magnitude depending on climate and building (e.g. Hoyt, Arens & Zhang, 2015, *Building and Environment*, "Extending air temperature setpoints"; **verify before citing**). No fixed percentage is claimed for this device.

---

## 7. Stretch

| ID | Function |
|---|---|
| X1 | Multi-feature personal residual model (temperature, humidity, rate of change, clothing), compared prospectively against the offset and kept only if better |
| X2 | Multi-day unresolved-discomfort history and time-lapse (labelled simulated) |
| X3 | "Move away from window/radiator" advice (requires a real reference measurement elsewhere in the room) |
| X4 | Probable sun-load event (camera brightness + sustained temperature rise) |
| X5 | Temperature-aware burst ventilation (not air-quality monitoring) |
| X6 | Smart-building view (illustrative) |

---

## 8. Demo (3 min)

Real observations and simulated parts are always labelled.

1. **Real readings:** temperature and humidity live from the device (heating mode).
2. **Personal:** Tuan Anh and Minh each report how they feel in the same real conditions; the dashboard shows different predictions and offsets.
3. **Perception:** the camera recognises clothing on the device (`outer_layer` / `no_outer_layer`).
4. **Optional suggestion:** the person who feels cold without a layer gets "Add a layer?"; responses "Do it / Not possible / Not now" are shown.
5. **Action and follow-up:** they put a layer on; the camera confirms; follow-up feedback; the offset and fix experience update (with uncertainty).
6. **Room level (labelled simulated coworkers):** the room recommendation in heating mode stays lower because the cold person was solved with a layer; a person with unresolved discomfort stays visible; "Agree" button.
7. **Privacy and energy:** close the shutter → camera-off detected; privacy receipt; energy panel's three layers.

**If the venue is too warm for a genuine "cold" report:** demonstrate the warm branch live ("room may be overheated → could lower heating") and show a **recorded real cold episode** from earlier in the weekend (for example collected near the entrance), clearly labelled as recorded. A hairdryer or ice pack may be used only as a labelled sensor test.

---

## 9. Judging fit

| Criterion | Weight | What makes it convincing |
|---|---|---|
| Technical implementation & edge AI | 30% | On-device clothing recognition with held-out evaluation; personal offset with prospective evaluation; fix experience learning; two processors working together |
| Environmental & social impact | 30% | Mode-aware energy logic; user agency (optional suggestions, human agreement); persistent discomfort visible; works in ordinary offices |
| Creativity & innovation | 20% | Personal + perceptive + adaptive comfort advice; unresolved discomfort as a room input; verifiable privacy receipt |
| Working prototype & demo | 20% | One genuine adaptive interaction on real hardware; room level clearly separated |

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Classifier only recognises one jacket | Varied consented data; held-out-person test; `uncertain` |
| Inflated accuracy | Hold out whole sessions |
| Classifier takes too long | 14:00 gate; dashboard clothing input |
| Personal offset not better than baseline | Report it honestly; that's still a valid finding |
| Venue too warm for a real cold report | Warm branch live; recorded real cold episode |
| Energy claims challenged | Three-layer panel; no fixed percentage |

---

## 11. Deliverables
1. Working prototype and the demo above.
2. Junction submission: description, ~2-minute video, photos, architecture diagram, GitHub repo with README (setup, data flow and privacy limits, evaluation method and results, assumptions).
3. **Arduino Project Hub** page tagged *Junction Finland 2026*.

## 12. Sources
- CBE, Personal Comfort Systems (research context; includes active heating/cooling devices that differ from this advice-only prototype): https://cbe.berkeley.edu/research/personal-comfort-system/
- `pythermalcomfort` documentation (PMV inputs and assumptions)
- Hoyt, Arens & Zhang (2015), "Extending air temperature setpoints: Simulated energy savings and design considerations for new and retrofit buildings", *Building and Environment* (verify before citing)
