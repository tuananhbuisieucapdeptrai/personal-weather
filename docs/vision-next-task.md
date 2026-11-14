# Minh: production vision module and hardware acceptance

Implemented 2026-11-14. Board deployment and accuracy validation are pending.

## Implemented

- `vision.start()`, `stop()`, `latest()` and separate `diagnostics()`.
- Capture in a spawned child process; import never starts capture. Frames remain in the child, never saved or transmitted. Only scalar state crosses the pipe.
- Explicit startup and restart; stop waits for exit, terminating a blocked worker if necessary. Eight-second no-progress watchdog.
- Calibrated shutter detection on captured frames; sustained darkness releases capture and latches `shutter` until explicit restart.
- Experimental OpenCV built-in HOG presence detector, with inference timing and a three-observation filter for changes. First observation initializes the filter.
- Clothing always `uncertain`, confidence null. No classifier result is invented.
- Separate acceptance app using the existing API control validation/callback. Tuan Anh's main.py, mocks, comfort, suggestions, sensing and contracts are untouched.

## Integration notes for Tuan Anh

Guard application startup with `if __name__ == '__main__':` because multiprocessing spawn imports the main module. Importing vision is safe; starting it at module top level is not. Call start on explicit app/operator intent, never repeatedly in the loop. latest returns a copy of the four-field contract without camera I/O or process waits.

During initialization the contract remains off/unknown until the first inference; diagnostics.phase is starting. Check diagnostics.capture_open as well when describing physical capture during initialization. Errors clear stale evidence and expose the cause in diagnostics.error. stop can take several seconds for a blocked driver, so invoke controls outside the main event loop if needed.

Wire `api.ControlState(on_camera=lambda on: vision.start() if on else vision.stop())`. Display measured vision status separately from the requested camera_setting. The test app is not the final dashboard and does not send summaries to the hub.

## Deploy on UNO Q

1. Build with `./tools/build_vision_app.ps1` in Windows PowerShell. The resulting `vision-check.zip` packages canonical modules; rebuild after changes. Do not commit the generated ZIP.
2. In App Lab, stop **Personal Weather Camera Check**. It owns the camera and port 8000.
3. Go to Apps, import `vision-check.zip`, open **Personal Weather Vision Check**, and Run.
4. Open http://pw-desk.local:8000 (fallback http://192.168.0.85:8000). The title must be **Production vision module check**. Camera begins off.
5. Open shutter and click Camera on. Confirm diagnostics phase=running, capture_open=true, increasing frames/inferences, error=null. Record inference_ms, mean_inference_ms and max_inference_ms.
6. Test empty frame, standing person and normal seated desk position for 10 seconds each. Repeat with both users. Compare actual presence to vision.present, including false positives.
7. Close shutter: time capture release and check camera=shutter, capture_open=false. Reopen without clicking: frame count must stay stopped. Explicit Camera on must resume.
8. Start with shutter still closed: it must stop again. Repeat off/on and test the darkest expected room with the lens uncovered. Check physical camera indicator if present.
9. Test manual outer/none/auto controls: manual source is displayed; auto returns uncertain until a classifier is installed.

## Verification and limitations

Local tests use Python 3.11.5 bundled with installed KiCad. Seven process lifecycle/filter tests passed, including crash, blocked stop, watchdog, latched shutter and explicit restart. Existing shutter self-test and contracts self-test also passed (26 valid examples accepted, 13 invalid rejected). These do not establish camera accuracy or real driver behavior.

HOG is a full-body baseline and may miss seated or occluded people. Source: https://docs.opencv.org/4.13.0/d5/d33/structcv_1_1HOGDescriptor.html . Benchmark on UNO Q before accepting presence detection. Heavy inference can delay shutter response; the watchdog is a failure bound, not a guaranteed three-second shutdown.

The calibrated dark-room sample was brighter than the normal-light sample. Repeat in the darkest real deployment setting. If presence fails, replace the detector or use the agreed knob-activity fallback. Clothing training/evaluation and LED rendering remain separate tasks.

Deployment status: not imported yet. Computer control returned App Lab accessibility text but an unrelated browser screenshot; clicking failed with `coordinate input geometry is unavailable`. Manual import is needed to continue. Nothing from this task has been pushed.

## v2 correction after real desk test

Minh reported HOG remained false despite changing position. Screenshot: capture on, error=null, 37 inferences, mean 186.09 ms and max 203.29 ms. This is a failed presence acceptance test, not a shutter failure.

v2 adds frontal-face detection as a presence cue and retains HOG only when no face is detected. It does not recognize identity. Diagnostics now include face_count, body_count (null when skipped), and presence_cue. A cue is the current raw detection; filtered present may take three observations to change. Looking away, occlusion, poor framing or lighting can still cause misses; test empty-chair false positives as well.

The model is loaded from runtime OpenCV data or python/models/haarcascade_frontalface_default.xml. Missing model produces an explicit error instead of silently running the failed HOG-only baseline. Network download of the official model was unavailable from this laptop session, so model availability on the board still needs confirmation. OpenCV reference: https://docs.opencv.org/4.13.0/db/d28/tutorial_cascade_classifier.html . Rebuild/import vision-check.zip; confirm UI title v2 and detector contains face + HOG v2. No hardware pass is claimed yet.

## v2 board acceptance: 2026-11-14 (supersedes pending deployment notes above)

Minh imported and ran v2. Screenshot showed present=true, face_count=1, presence_cue=face, camera=on, capture_open=true, error=null. Runtime model loading succeeded. Across 150 inferences, mean inference time was 264.2 ms and maximum 454.36 ms (1227 captured frames). These are inference durations, not end-to-end response latency.

Minh subsequently confirmed all four requested checks worked:
- Leaving the frame for 10 seconds produced present=false.
- Returning and sitting normally produced present=true.
- Closing the shutter produced camera=shutter and capture_open=false.
- Reopening alone kept capture stopped; explicit Camera on restarted it.

Result: camera lifecycle, basic presence/absence and shutter/restart PASS in the tested setup, using the production vision module through the acceptance dashboard. Nine local tests also passed. This is not a quantitative accuracy evaluation, clothing-classifier pass, darkest-room robustness pass, or integration with Tuan Anh's final main loop/dashboard. Exact shutter latency, closed-shutter restart, reboot/rejoin and quiet-office sound acceptance remain open.

Next Minh task: M2.1 LED face rendering plus executable tools/face_test.py. sketch.ino still contains its rendering TODO and face_test.py is only a docstring. Implement comfort/suggestion icons, feedback arrows/dot, DO/NO/LATER text, check, eye-off followed by corner dot, and off; preserve nonblocking sensor/knob/Bridge behavior. Verify visible output and buzzer commands on the UNO Q. Clothing dataset/training/evaluation remain separate work and the manual fallback remains available.

Git: vision work remains local and uncommitted as of this report. Tuan Anh's T1.1-T1.3 files were not changed.
