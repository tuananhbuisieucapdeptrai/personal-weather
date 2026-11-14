# Hub (laptop)

Owner: Tuan Anh (T4.1–T4.4, T5.2–T5.3). Server + dashboard + room add-ons (A1–A4).

- Listens on port **8080**. `POST /summary` receives device summaries (spec C8); the hub stamps **receipt time**, and a summary older than 2 minutes is stale (person treated as absent).
- Serves the dashboard. Everything simulated, recorded, accelerated or modelled carries its label (see `docs/interfaces.md` section 0.3).

## Run

```bash
python3 hub/server.py            # listens on 0.0.0.0:8080
```

- `POST /summary` → 204 (400 + reason if the body breaks the C8 contract)
- `GET /summaries` → every pid with `age_s`, `stale`, `present_effective`
- `DELETE /summaries/<pid>` → remove a synthetic test entry
- `GET /ping` → liveness

Stdlib only.

## Dashboard (T4.1)

Open `http://<laptop>:8080/`. It reads the device at `http://pw-desk.local:8000` by default; add `?device=http://<ip>:8000` to pick another one.

One screen, core function only:
- **How the person feels** (❄️ / 🙂 / ☀️), the temperature and their comfort range.
- **One action line**, shown only when needed: a suggestion with the knob choices (NO / LATER / DO), a check-back countdown, or "Did it help?".
- **Two numbers:** answers predicted right (vs the formula alone), and how often the fix helped.
- **Controls:** Person, Wearing, Season, Camera.
- **Privacy:** one line, plus the exact message sent.
- **Technical details:** collapsed.

Data labels always show: Live / Demo data / Sped up.

This is the desk owner's own view. The room view (A1–A4) uses hub summaries only.

**On the laptop without the board:**
1. Run `python3 device/python/main.py --mock --demo`.
2. Open `http://127.0.0.1:8080/?device=http://127.0.0.1:8000`.

## Room view (T4.3 + T4.4)

Open `http://<laptop>:8080/room`. It uses **only** the anonymous desk summaries: no names, votes or images.

- **Recommendation (A1):** each person counts as OK at a setpoint if it's inside their comfort range, or inside their range with a layer when they have one.
  - Heating takes the *lowest* setpoint that suits everyone present; cooling takes the *highest*; with an unknown season there's no recommendation.
  - If nobody fits everywhere, it picks the setpoint that suits the most people and lists who is still uncomfortable.
  - It proposes only changes of 0.5 °C or more. **Nothing changes until someone clicks Agree,** and the thermostat is then changed by hand.
  - After an agreement there's no new proposal for 90 minutes, unless people arrive or leave. With `--demo` this is 60 s, labelled "Sped up".
- **Simulated coworkers (A2):** three synthetic people, each tagged **SIM**, switched on and off on the page. The page shows "Includes simulated coworkers" while they're on.
- **Thermostat now:** enter the real setting with − / +. This isn't an agreement.
- **Uncomfortable with no free fix (A3):**
  - One bar per person: the minutes they were present and uncomfortable with no feasible fix, including after saying "not possible".
  - Bars stay after the person leaves, and there's no single fairness score.
  - In the fallback recommendation each person weighs 1 + minutes/30, at most 3.
  - 20+ unresolved minutes since the last agreement allow an early re-check.
- **Energy (A4),** three separate layers:
  - **MEASURED:** what the hub saw (people present, comfortable, with a free fix, with no fix).
  - **PROPOSED:** the recommendation or agreement. It needs a person, and the thermostat itself isn't verified.
  - **MODELLED:** research context only, with no percentage claimed. Hoyt, Arens & Zhang (2015), *Building and Environment* 88:89–96, doi:10.1016/j.buildenv.2014.09.010.

Run it with:

```bash
python3 hub/server.py --demo
```

The room JSON is at `/room.json`. Tests: `python3 -m unittest tools/tests/test_room.py`.
