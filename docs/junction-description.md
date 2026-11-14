# Junction submission text (draft)

Paste-ready text for the Junction platform. Fill every ⏳ before submitting.

**Challenges:**
- Main: Make Europe Green through Edge AI using Arduino
- Tech: Best use of Arduino UNO Q

**Links:**
- Repo: ⏳
- Video (~2 min): ⏳
- Arduino Project Hub (tag *Junction Finland 2026*): ⏳

---

## Name
Personal Weather

## Tagline (short field)
A privacy-first Edge AI desk companion that learns how *you* feel in a shared room, suggests a jacket before anyone turns up the heating, and helps the office agree on a lower setpoint. Images never leave the desk.

## Description

**The problem.** In a shared office, one thermostat serves people who feel the same room very differently. The usual answer to "I'm cold" is more heating for everyone. In a Finnish winter that's a lot of energy, and it often still leaves someone uncomfortable.

**Our solution.** Personal Weather is a small device on each desk, built on the **Arduino UNO Q**.
- **It learns you.** A standard comfort formula (ISO 7730) is corrected by a personal offset, learned from your own knob feedback. Two people in the same conditions get different predictions.
- **It sees, privately.** A camera detects whether someone is at the desk and whether they're wearing an outer layer, using a small model on the device. Frames stay in memory on the device and are never stored or sent. A physical shutter turns the camera off, and the device notices.
- **It suggests free fixes.** "Put on a layer?" appears on the LED face. You answer with the knob: *Do it*, *Not now* or *Not possible*, with no penalty. A few minutes later it asks whether it helped, and keeps an honest record of what works for you.
- **It respects the season.** In heating mode, a layer replaces a request for more heat, and warm people show the heating could go down. In cooling mode it's the reverse. If the season is unknown, it makes no energy claims.

**Automatic, and respectful.**
- It predicts comfort on its own from temperature, humidity and what you're wearing.
- One optional knob click ("I'm cold") corrects it and teaches it about you.
- Putting on the suggested layer is enough; the camera sees it.
- We deliberately do **no emotion recognition**: the EU AI Act prohibits it at work.

**Room level.** Each desk sends only a pseudonymous comfort summary to a hub on the room's laptop: an anonymous ID, whether someone is there, a comfort range, and whether they're uncomfortable. The hub then:
- recommends the **lowest heating setpoint that suits everyone present**, counting the free fixes each person can actually make;
- keeps anyone with **unresolved discomfort visible**, instead of averaging them away;
- changes nothing until a person clicks **Agree**.

**Honest by design.**
- Energy is shown as **Measured / Proposed / Modelled**, cited to building-simulation research, with no made-up percentage.
- Simulated coworkers and sped-up demo timers are always labelled.
- The personal model is evaluated **prospectively**: every prediction is logged before the vote that tests it.

**Edge AI on the UNO Q.**
- The microcontroller drives the Modulino sensors, knob, buzzer and LED face.
- The Linux side runs vision, the comfort model, suggestions and learning, all locally.
- One full comfort estimate takes **3.1 ms** on the board.

**Results so far.**
- In simulation, the personal offset raised 3-class accuracy from 0.48 to **0.73** for someone who runs cold, and from 0.46 to **0.66** for someone who runs warm. It cost a little for an average person (0.75 → 0.73), and we report that too.
- Live results from our own feedback: not yet meaningful. One evening of test votes, archived rather than counted; the method is in place.
- On-device clothing detection: our first trained model scored 92.5 % on held-out photos, but **failed live** (it learned colour and sleeve shortcuts). We replaced it with **zero-shot CLIP**: no training on our photos, **40/40 on the held-out set**, about 0.5 s per check on the UNO Q. It still misses open jackets, and we say so.

**Compared with what exists.**
- Smart thermostats optimise the building, not the person.
- Comfort apps answer "I'm cold" by spending HVAC energy and need building-system integration.
- Personal heaters and fans use energy too.
- Personal Weather offers a **free fix first**, learns each person, keeps images on the device, and works with an ordinary thermostat.

**Why it matters for a greener Europe.** The cheapest kilowatt-hour is a jacket. Personal Weather turns "I'm cold" into a free, optional fix first, and into a fairer, lower setpoint the whole room agrees on. It works in ordinary offices with an ordinary thermostat, with no cloud and no big-tech platform.

## Built with
Arduino UNO Q · Arduino App Lab · Modulino Thermo / Knob / Buzzer · OpenCV · Python (standard library) · ISO 7730 PMV

## Team
Tuan Anh (software) · Minh (hardware)
