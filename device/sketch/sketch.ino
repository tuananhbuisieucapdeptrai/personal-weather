// build: 2026-11-15T00:18:55
// Personal Weather: microcontroller side of the UNO Q.  Owner: Minh (M1.2, M1.3, M2.1).
//
// Reads Modulino Thermo (1 Hz) and Knob, drives the onboard LED matrix face and the
// Modulino Buzzer. Messages to/from Linux: docs/interfaces.md section 0.2.
//
// Status: kickoff version. Sensing, knob, click and Bridge mapping are implemented and
// checked by device/python/board_check.py. M2.1 renders faces without blocking
// the loop; tools/face_test.py exercises the real display and buzzer.
//
// Bridge rules (docs/kickoff-guide.md, item 1):
//   - notify in both directions; handlers registered with provide_safe
//   - NEVER delay() in loop(): provide_safe handlers only run between loop() passes
//   - never Bridge.call / Monitor.print inside a handler
//
// NOTE: App Lab generates app.yaml (in device/) and sketch/sketch.yaml when the app is
// created. Add the Modulino and Arduino_RouterBridge libraries there if App Lab asks.

#include <Arduino_RouterBridge.h>
#include <Modulino.h>
#include <Arduino_LED_Matrix.h>
#include "faces.h"
#include <atomic>

// Read-only diagnostic served independently of the main sketch loop.
std::atomic<int> startupStage{0};
int faceCheckStage() { return startupStage.load(); }

Arduino_LED_Matrix matrix;
uint8_t displayPixels[104];
uint8_t previousPixels[104];
unsigned long faceSinceMs = 0;
unsigned long lastDisplayMs = 0;

// ---- Tuning (set these from board_check.py output) --------------------------
#define COUNTS_PER_DETENT 1     // raw knob counts per physical click
#define KNOB_DIRECTION    1     // set to -1 if clockwise makes the raw count go DOWN
#define DEBUG_KNOB_RAW    1     // 1 = also send "knob_raw" (calibration only); set 0 after kickoff
#define DEBUG_FACE_ACK    1     // 1 = send "face_ack" counter so Linux can verify Python->sketch

#define CLICK_FREQ_HZ     4000
#define CLICK_MS          5
#define CLICK_MIN_GAP_MS  40
#define PRESS_DEBOUNCE_MS 200
#define ENV_PERIOD_MS     1000

ModulinoThermo thermo;
ModulinoKnob   knob;
ModulinoBuzzer buzzer;

bool thermoOk = false, knobOk = false, buzzerOk = false;

// ---- Knob state ----------------------------------------------------------------
int  lastRaw = 0;
int  lastObservedRaw = 0;           // independent of detent accumulation
int  pos = 0;                       // clamped to -1 / 0 / +1
bool wasPressed = false;
unsigned long lastPressMs = 0;
unsigned long lastClickMs = 0;

// ---- Face state (M2.1 draws from these) -----------------------------------------
String currentFace = "smile";
int    facePos = 0;
String faceText = "";
int    faceCount = 0;
int    faceCountSent = 0;

// ---- Linux -> sketch handlers (provide_safe: they will touch the matrix/buzzer) --
void onFace(String name)       { currentFace = name; faceSinceMs = millis(); faceCount++; }
void onFaceFeedback(int p)     { currentFace = "feedback"; facePos = p; faceSinceMs = millis(); faceCount++; }
void onFaceText(String text)   { currentFace = "text"; faceText = text.substring(0,8); faceSinceMs = millis(); faceCount++; }
void onBeep(String name) {
  faceCount++;
  if (!buzzerOk) return;
  if      (name == "chirp") buzzer.tone(2500, 60);
  else if (name == "chime") buzzer.tone(1500, 150);
  else if (name == "low")   buzzer.tone(400, 250);
}

void playClick() {
  unsigned long now = millis();
  if (!buzzerOk || now - lastClickMs < CLICK_MIN_GAP_MS) return;
  lastClickMs = now;
  buzzer.tone(CLICK_FREQ_HZ, CLICK_MS);
}

void setup() {
  Bridge.begin();                   // blocks until the Linux side is up
  Bridge.provide("face_check_stage", faceCheckStage);
  // Discover I2C modules before starting the matrix refresh machinery. On the
  // tested UNO Q, matrix-first startup missed modules; this order found all three.
  startupStage.store(3); // entering Modulino bus initialization
  Modulino.begin(Wire1);            // UNO Q Qwiic connector uses the secondary I2C bus
  startupStage.store(4); // entering Thermo initialization
  thermoOk = thermo.begin();
  startupStage.store(5); // entering Knob initialization
  knobOk   = knob.begin();
  startupStage.store(6); // entering Buzzer initialization
  buzzerOk = buzzer.begin();
  startupStage.store(7); // reading initial knob position
  if (knobOk) lastObservedRaw = lastRaw = knob.get();

  startupStage.store(1); // entering matrix.begin
  matrix.begin();
  startupStage.store(2); // entering grayscale configuration
  matrix.setGrayscaleBits(1);
  memset(previousPixels, 255, sizeof(previousPixels));
  faceSinceMs = millis();

  startupStage.store(8); // registering commands
  Bridge.provide_safe("face", onFace);
  Bridge.provide_safe("face_feedback", onFaceFeedback);
  Bridge.provide_safe("face_text", onFaceText);
  Bridge.provide_safe("beep", onBeep);
  startupStage.store(9); // setup complete
}

unsigned long lastEnvMs = 0;

void loop() {                       // no delay() anywhere
  startupStage.store(10); // loop: environment
  unsigned long now = millis();

  // --- Environment, 1 Hz, raw values; failed read -> send nothing ---
  if (now - lastEnvMs >= ENV_PERIOD_MS) {
    lastEnvMs = now;
    if (thermoOk) {
      float t  = thermo.getTemperature();
      float rh = thermo.getHumidity();
      if (!isnan(t) && !isnan(rh)) Bridge.notify("env", t, rh);
    }
    // Health beacon for board_check.py: which modules answered at startup.
    Bridge.notify("hw_status", (int)thermoOk, (int)knobOk, (int)buzzerOk);
#if DEBUG_KNOB_RAW
    Bridge.notify("knob_config", COUNTS_PER_DETENT, KNOB_DIRECTION);
#endif
  }

  startupStage.store(11); // loop: knob
  // --- Knob turn: clamp to -1..+1, send only on change, click on every detent ---
  if (knobOk) {
    int raw = knob.get();
    int diff = raw - lastRaw;
#if DEBUG_KNOB_RAW
    if (raw != lastObservedRaw) Bridge.notify("knob_raw", lastObservedRaw, raw);
#endif
    lastObservedRaw = raw;
    int steps = diff / COUNTS_PER_DETENT;
    if (steps != 0) {
      lastRaw += steps * COUNTS_PER_DETENT;
      playClick();
      int newPos = constrain(pos + KNOB_DIRECTION * steps, -1, 1);
      if (newPos != pos) {
        pos = newPos;
        Bridge.notify("knob_turn", pos);
      }
    }

    // --- Knob press: rising edge + debounce; reset position to 0 silently ---
    bool pressed = knob.isPressed();
    if (pressed && !wasPressed && now - lastPressMs > PRESS_DEBOUNCE_MS) {
      lastPressMs = now;
      Bridge.notify("knob_press");
      pos = 0;
    }
    wasPressed = pressed;
  }

#if DEBUG_FACE_ACK
  if (faceCount != faceCountSent) {
    faceCountSent = faceCount;
    Bridge.notify("face_ack", faceCount);
  }
#endif

  // Render at most 25 Hz; write only changed frames. Timers tolerate millis wrap.
  if (now - lastDisplayMs >= 40) {
    lastDisplayMs = now;
    Faces::render(displayPixels, currentFace.c_str(), facePos, faceText.c_str(), now-faceSinceMs);
    if (memcmp(displayPixels, previousPixels, sizeof(displayPixels)) != 0) {
      startupStage.store(12); // entering matrix.draw
      matrix.draw(displayPixels);
      startupStage.store(13); // matrix.draw returned
      memcpy(previousPixels, displayPixels, sizeof(displayPixels));
    }
  }
}
