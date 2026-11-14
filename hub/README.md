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

Stdlib only. The dashboard (T4.1) is not built yet.
