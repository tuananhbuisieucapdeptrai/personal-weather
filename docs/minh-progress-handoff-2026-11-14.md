# Minh progress and integration handoff — 14 November 2026

## Status

M2.1 display/sound acceptance and M2.2 Bridge acceptance were previously completed and pushed. Clothing data collection and offline model training are now complete for a small two-person prototype. Live clothing inference on UNO Q is **blocked**, not accepted. This report does not certify Tuan Anh's independently pushed work; remote integration must be verified after fetching.

## Completed in this work

- Built Fashionpedia preparation and scoring tools. Downloaded 72 outer and 100 none candidates; first-pass visual review excluded 37 unsuitable crops. The simple public-image baseline scored 14/27 (51.9%) and was not deployed.
- Built UNO Q clothing capture tooling. System SSH Python lacks OpenCV; capture succeeded through the existing Arduino Docker image, with a bind mount preserving photos on the board.
- Increased requested capture resolution to 1280x720. The camera actually supplied 640x480; native torso crops were 384x250. Images retain aspect ratio and JPEG quality 95. Frames are drained between saves to avoid stale poses.
- Collected local data: p1 is Minh; p2 is Tuan Anh. Prepared 240 training images: 60 per person per class. The source folder is named framing_test despite containing training batches. Excluded the first 17 sorted p1 outer framing images from the prepared copy; originals remain local.
- Collected 40 separate holdout images: 10 per person per class. A mistaken p2 outer batch was deleted and retaken. Local audit found none of those ten exact mistaken filenames and no byte-identical train/test duplicates.
- Trained a frozen ImageNet MobileNetV3 Small feature extractor with a learned two-class linear head. Labels are ordered [none, outer]. All 240 prepared images were used for training; the 40-image holdout was evaluated after training, not used for tuning.
- Exported TorchScript model to device/python/models/clothing.ts. Checked export output parity and deployment preprocessing parity locally.
- Integrated inference into the camera worker and built Clothing Check v3. Fixed a packaging bug that previously omitted the model directory when the optional face XML was absent.

## Offline results

| Actual / predicted | none | outer |
| --- | ---: | ---: |
| none | 20 | 0 |
| outer | 3 | 17 |

Accuracy: 37/40 = 92.5%. Outer recall: 17/20 = 85%. This is a small two-person test, not a general accuracy claim. Training loss rounded to zero; this is not evidence of broad generalization. Training jackets are predominantly dark and long-sleeved, and none examples predominantly short-sleeved, so garment/color/sleeve shortcuts are a material risk.

## Current blockers on UNO Q

1. **PyTorch native-library failure.** Initial unqualified torch installation pulled CUDA packages and exhausted storage. CPU requirements now request torch==2.15.0+cpu from the official CPU index. That installation succeeded, but importing it in the app fails with `libtorch_cpu.so: undefined symbol: sbgemm_`. The trained model has not successfully run on the board. An ONNX/OpenCV alternative was proposed but has NOT been implemented or verified.
2. **Camera opening failure.** Latest state reported `RuntimeError: No readable camera; stop other camera apps and check USB/power`, frames=0, capture_open=false. Check USB camera/hub power, device availability inside the running container, and competing apps.
3. **Presence gating.** Clothing inference executes only when the raw face/HOG detector detects a person. Looking away or failed detection resets clothing stability. Earlier uncertain states were also affected by this gate.

The hotspot changed the board address; direct-IP access subsequently worked. This is separate from the above runtime errors. No private network credentials are included here.

## Remaining work

- Resolve CPU native-library compatibility or export and validate ONNX with the available OpenCV runtime; reuse trained weights rather than retrain unnecessarily.
- Restore camera access and verify actual capture resolution and torso framing match collection.
- Validate inference on UNO Q, measure model and total inference latency, memory, startup time, and worker watchdog behavior.
- Calibrate an uncertainty threshold using separate validation data. Current threshold 0.8 plus three consistent observations is provisional; softmax scores are not calibrated confidence. Do not tune against the existing holdout.
- Test both people with/without layers, missed presence, empty scenes, lighting changes, camera off, and physical shutter shutdown/reopen behavior. Record abstentions as well as errors. Offline 92.5% does not describe the thresholded live pipeline.
- Integrate with Tuan Anh's latest hub/API work after resolving any Git conflicts. Preserve interface contracts and manual clothing fallback.
- Update final task acceptance and results only after physical tests pass.

## Files and reproduction

- tools/eval/capture_clothing.py: board capture; run through Arduino's existing Python container with camera device and persistent output bind mount.
- tools/eval/train_clothing_transfer.py: training and final holdout evaluation. First run requires torchvision pretrained weights download.
- tools/eval/export_clothing.py: export existing checkpoint; does not retrain.
- device/python/clothing.py and vision.py: runtime model/preprocessing and camera integration.
- tools/build_vision_app.ps1: packages canonical source and models into vision-check.zip.
- Local private files: tools/eval/data/desk/prepared_train, training_manifest.csv, holdout_jacket4, holdout_top4, and transfer_model (checkpoint, predictions, results). They are intentionally excluded from Git.

Do not commit personal photos, virtual environments, generated ZIPs, runtime pseudonyms, or local agent configuration. The approximately 4 MB exported clothing.ts model is the deployment artifact for this prototype; it is included with the code. It contains learned parameters, not source photos.

## Merge note

At preparation time this agent could read Git status but could not write .git/FETCH_HEAD due to checkout permissions. No fetch, merge, commit or push was completed by the agent. Run the supplied Git commands in the owner's PowerShell and inspect the final status. Do not force-push over Tuan Anh's work.
