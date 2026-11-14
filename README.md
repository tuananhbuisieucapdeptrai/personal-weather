# Personal Weather

> *The cheapest kilowatt-hour is a jacket.*

Privacy-first Edge AI desk companion on the Arduino UNO Q. It learns how each person experiences the same room, offers optional free comfort fixes, and helps a shared room agree on a heating or cooling setting that needs less energy. Images never leave the desk.

Junction 2026 · The Green European Renaissance (Arduino) · Tuan Anh (software), Minh (hardware)

- Product spec: [docs/spec.md](docs/spec.md)
- Implementation plan: [docs/implementation-plan.md](docs/implementation-plan.md)
- **Interfaces (read before writing code):** [docs/interfaces.md](docs/interfaces.md)

## Layout

```
device/              App Lab app that runs on the UNO Q
  sketch/            (Minh) microcontroller: Modulinos, LED face, buzzer, knob
  python/            Linux side of the UNO Q
    main.py          (Tuan Anh) main loop
    contracts.py     (shared) message contracts as executable checks
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

Check the contracts at any time:

```bash
python3 device/python/contracts.py
```

*Setup, data flow and privacy limits, evaluation method and results, and assumptions are added here during Block 5 (T5.4).*
