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
