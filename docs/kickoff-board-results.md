# UNO Q kickoff run — 2026-11-14

Imported Personal Weather Kickoff into Arduino App Lab 0.12.0 and compiled/uploaded on UNO Q platform 1.1.0. Reinstalled Arduino_Modulino 0.9.0 through the library manager to resolve transitive dependencies.

The Python app started successfully. Retested after explicitly selecting `Modulino.begin(Wire1)` for the UNO Q Qwiic connector.

| Check | Observed result |
| --- | --- |
| Linux-to-sketch messages | PASS: 17 of 17 acknowledged |
| Thermo detection | FAIL |
| Knob detection | FAIL |
| Buzzer detection | FAIL |
| Environment readings | FAIL: 0 messages in 10 seconds |
| Knob calibration/behaviour | SKIP: modules not detected |
| Sound quality | Not verified |

Next: with board power disconnected, verify the Qwiic cable from UNO Q to the Modulino chain and each module connection. A USB hub connection alone does not connect these I2C modules. Restore power and rerun the app. Do not mark kickoff items 1–3 complete yet.

The LED face renderer and production vision implementation remain unfinished; this run only validates the kickoff harness.

## Retest after connecting the Modulinos

All three modules detected successfully. Environment: 10 messages in 10 seconds, 24.5 degC and 29.3% RH; decimal values preserved. Linux-to-sketch messages: 17/17 acknowledged.

Knob calibration received no raw changes during its 10-second window; this does not establish a hardware failure because operator timing was not confirmed. Knob behaviour was skipped. Repeat with Minh ready to follow the timed prompts. Sound quality remains unverified.

## Successful timed retest

All 13 automated checks passed (board log start: 2026-11-14 08:54:36). Thermo: 23.3 degC, 30.4% RH; 10 readings in 10 seconds. All 17 Linux-to-sketch commands acknowledged. Knob calibration confirmed one count per notch, clockwise positive: retain COUNTS_PER_DETENT=1 and KNOB_DIRECTION=1. Clamp, single press, position reset, held press, and fast spin checks passed (7 turn events, zero invalid messages).

Minh confirmed individual clicks on slow turns and repeated clicks on fast turns. He requested approximately 30% lower volume, then declined the proposed shorter-duration workaround because the Modulino API has no volume setting. Sound settings remain unchanged; quiet-office acceptance is not explicitly confirmed. Debug flags remain enabled pending that review. Earlier failures above are historical and superseded by this successful run.
