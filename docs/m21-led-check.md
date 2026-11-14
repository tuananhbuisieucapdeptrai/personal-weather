# M2.1 LED face implementation and acceptance

Implementation compiles and runs on the board. Diagnostics v4 completed all 18 commands with 92 environment messages, 4 knob events and zero invalid messages. All three modules were detected, with no stale-environment warnings. Complete physical visual/sound acceptance remains pending.

First board compile exposed a missing RouterBridge dependency: platform 1.1.0 selected its stub header and requested Library Manager installation. Added Arduino_RouterBridge 0.4.3 explicitly to sketch.yaml and rebuilt the archive. Earlier handoff statements that the platform supplied the implementation were incorrect for this profile. Rebuild success remains pending; if additional dependencies are requested, install RouterBridge via App Lab's library manager with dependencies and retain the generated profile.

- UNO Q 13x8 buffer using Arduino_LED_Matrix, setGrayscaleBits(1), draw(buffer). API reference: https://docs.arduino.cc/tutorials/uno-q/user-manual/
- Pure rasterizer in device/sketch/faces.h; refresh capped at 25 Hz, only changed buffers written. No delay in sketch. Existing Wire1 sensing, calibrated knob and buzzer settings preserved.
- Smile, sun, snowflake, check; left/dot/right feedback; blinking layer icons with plus/minus; DO/NO centered, LATER scrolling; eye-off for 3 seconds then bottom-right dot; off blank.
- Uppercase letters, digits and spaces supported, at most 8 characters. Short text centered; long text scrolls. Each face command restarts its animation; beep commands do not reset it.
- tools/face_test.py cycles every face and beep contract through bridge_io, monitors environment freshness, and counts knob events. Printed sequence is not proof of visible output.

## Run

1. Build using ./tools/build_face_app.ps1 (Windows PowerShell); face-check.zip is generated, not source to commit.
2. Stop the current vision test in App Lab before switching apps. Import face-check.zip as Personal Weather Face Check. Run it and keep the Python console visible.
3. Diagnostics v4 waits for all three modules and fresh environment readings, then starts after 3 seconds. Watch the matrix as each WATCH label appears over about 95 seconds. Turn and press the knob during scrolling text and the final smile; confirm clicks remain responsive. If the readiness gate stays closed, inspect HEALTH and SKETCH output; do not interpret the idle smile as a completed test.
4. Confirm orientation and legibility of all icons, plus versus minus, arrows, text, blinking, eye-off-to-dot at 3 seconds, blank state and all three buzzer commands. Sensor freshness warnings must be investigated.
5. Send compiler errors if any; otherwise report specific unreadable/reversed/missing graphics. Nine previous vision tests do not validate this sketch.

The matrix header is expected from the UNO Q platform, not a separate R4 library. A local C++ toolchain was unavailable; compile on UNO Q/App Lab is required. Python syntax and git diff checks passed. Tuan Anh's production main and T1.1-T1.3 code were not edited.

Integration note: copy faces.h with sketch.ino when updating production. Keep sending face commands on changes rather than every main-loop tick, because resending restarts animations. LED changes do not implement the product state machine.

Follow-up compile found Arduino_RPClite.h missing. The profile now explicitly lists Arduino_RPClite 0.3.0, MsgPack 0.4.2, DebugLog 0.8.4, ArxTypeTraits 0.3.2 and ArxContainer 0.7.0 alongside RouterBridge 0.4.3. Rebuilt face-check.zip with diagnostics v2. Hardware compilation and acceptance remain pending. Dependency versions cross-checked against https://github.com/arduino/ArduinoCore-zephyr/issues/542 .

Diagnostics v2 ran on the board but received zero hw_status, face_ack, env or knob messages throughout the sequence. This does not establish a module failure or successful rendering. Diagnostics v3 adds a read-only atomic startup-stage RPC served on the Bridge thread and waits for a fresh hardware heartbeat before starting the visual sequence. Stages: 1 matrix.begin, 2 grayscale, 3 Modulino bus, 4 Thermo, 5 Knob, 6 Buzzer, 7 initial knob read, 8 command registration, 9 setup complete, 10 environment loop, 11 knob loop, 12 matrix.draw, 13 draw returned. A missing RPC may indicate an older/not-running sketch or incomplete Bridge startup; hardware compilation and root cause remain unverified.

Live App Lab comparison: v3 compiled/uploaded (125616 bytes flash, 51164 bytes RAM) but face_check_stage was unavailable and all hardware messages absent. The original kickoff app then reported PASS for Thermo, Knob and Buzzer. Its build used RouterBridge 0.4.4 and RPClite 0.3.1, unlike the face-check pins 0.4.3/0.3.0. Updated the profile and archive to the observed working versions and imported/reran the corrected app. Runtime retest pending.

Corrected-version runtime result: face_check_stage responds (stage 11), hw_status arrives every second, and face_ack increments with commands (observed through 10). The unavailable-method/absent-heartbeat problem is resolved in this retest. Module discovery remains unresolved: first run (False, False, False), repeat startup (False, False, True). No env messages. Baseline kickoff had all three found immediately beforehand. Do not mark M2.1 accepted; physical icon verification and reliable module discovery are still pending.

Minh subsequently confirmed changing icons on the physical matrix. This confirms visible rendering, but not every icon, text orientation, timed transition or sound. Diagnostics v4 moves matrix initialization after module discovery and requires all modules plus fresh environment data before running the sequence. This startup-order change is a hypothesis under board test, not yet an established fix.

## Verified v4 result — 2026-11-14

App Lab ran diagnostics v4 after importing the rebuilt archive. Initializing the modules before the matrix resolved discovery in this run: HEALTH remained `(True, True, True)`, environment readings arrived at 1 Hz, and the sequence finished with **92 environment messages, 4 knob events, face_ack=18, invalid_messages=0**. No stale-environment warnings appeared. The sketch RPC remained responsive (stage 11). This verifies concurrent communications, sensor delivery and knob-event delivery during the display/sound sequence; it does not certify the physical graphics or sound quality. Repeat-start reliability remains untested for v4.

- [x] Board compile and app startup.
- [x] Bridge probe and all 18 command acknowledgments.
- [x] Thermo, Knob and Buzzer detected together.
- [x] Live environment readings throughout the sequence.
- [x] Knob events received during the sequence.
- [x] Changing physical icons confirmed by Minh in the preceding run.
- [x] Minh confirms every icon/text orientation, PLUS/MINUS blink and LATER scroll (2026-11-14).
- [x] Minh confirms eye-off changes to bottom-right dot after 3 seconds and blank clears the matrix (2026-11-14).
- [x] Minh confirms chirp, chime and low beep are distinct and knob clicks responsive (2026-11-14).

M2.1 accepted by Minh after physical inspection. Changes are local and have not been committed/pushed by this test run.
