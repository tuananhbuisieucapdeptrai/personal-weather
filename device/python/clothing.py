"""Local clothing inference. Default: zero-shot CLIP (ClipClothing, below). Fallback: Minh's trained
MobileNet head (M2.3/M2.4), which failed a live test (colour/sleeve shortcuts). Scores are uncalibrated.

Runs Minh's trained MobileNetV3-Small classifier from models/clothing.onnx with OpenCV DNN
when available, otherwise ONNX Runtime (App Lab's OpenCV is built without dnn; onnxruntime
is in python/requirements.txt). PyTorch is NOT needed on the board (it fails to import there:
libtorch_cpu.so undefined symbol sbgemm_). The ONNX file is converted from the original
TorchScript (models/clothing.ts) by tools/eval/export_clothing_onnx.py, which checks parity.

Same preprocessing as training (torchvision MobileNet_V3_Small weights.transforms()):
torso crop -> RGB -> shorter side 256 (bilinear) -> centre 224x224 -> /255 -> ImageNet mean/std.
Labels [none, outer]. Below SCORE_MIN -> 'uncertain'; a label must repeat STABLE_N times to be
adopted, and then stays until another label repeats STABLE_N times (hysteresis).
"""
from __future__ import annotations

import time
from pathlib import Path

LABELS = ("none", "outer")
SCORE_MIN = 0.8          # provisional (Minh): not calibrated; do not tune on the holdout
STABLE_N = 3
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
MODEL = Path(__file__).parent / "models" / "clothing.onnx"


def torso_crop(frame):
    h, w = frame.shape[:2]
    return frame[int(.38 * h):int(.90 * h), int(.20 * w):int(.80 * w)]


class MobileNetClothing:
    def __init__(self, model_path: Path = MODEL):
        import cv2
        import numpy as np
        self.cv2, self.np = cv2, np
        if not Path(model_path).exists():
            raise FileNotFoundError(f"{model_path} missing: run tools/eval/export_clothing_onnx.py")
        if hasattr(cv2, "dnn"):                      # laptop OpenCV builds
            self.backend = "opencv-dnn"
            net = cv2.dnn.readNetFromONNX(str(model_path))

            def run(x):
                net.setInput(x)
                return net.forward()
        else:                                        # App Lab's OpenCV has no dnn module
            import onnxruntime as ort
            self.backend = "onnxruntime"
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2            # leave cores for the camera loop and app
            sess = ort.InferenceSession(str(model_path), opts, providers=["CPUExecutionProvider"])
            name = sess.get_inputs()[0].name

            def run(x):
                return sess.run(None, {name: x})[0]
        self._run = run
        self.mean = np.array(MEAN, np.float32)
        self.std = np.array(STD, np.float32)
        self.candidate, self.hits = None, 0
        self.stable = "uncertain"
        self.last_ms = 0.0

    def blob(self, crop_bgr):
        cv2, np = self.cv2, self.np
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        size = (256, int(256 * h / w)) if w <= h else (int(256 * w / h), 256)   # (width, height)
        rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_LINEAR)
        left, top = round((size[0] - 224) / 2), round((size[1] - 224) / 2)
        x = rgb[top:top + 224, left:left + 224].astype(np.float32) / 255.0
        x = (x - self.mean) / self.std
        return np.ascontiguousarray(x.transpose(2, 0, 1)[None])

    def scores(self, crop_bgr):
        """Softmax over [none, outer] for an already-cropped torso image."""
        z = self._run(self.blob(crop_bgr))[0]
        e = self.np.exp(z - z.max())
        return e / e.sum()

    def predict(self, frame):
        """Full camera frame -> (stable label or 'uncertain', top score, milliseconds)."""
        began = time.monotonic()
        s = self.scores(torso_crop(frame))
        i = int(s.argmax())
        score = float(s[i])
        label = LABELS[i] if score >= SCORE_MIN else "uncertain"
        self.hits = self.hits + 1 if label == self.candidate else 1
        self.candidate = label
        # Hysteresis: a stable label stays until a DIFFERENT confident label repeats STABLE_N
        # times; single odd or low-score frames never flip it back to 'uncertain'.
        if label != "uncertain" and self.hits >= STABLE_N:
            self.stable = label
        self.last_ms = (time.monotonic() - began) * 1000
        return self.stable, score, self.last_ms

    def reset(self):
        self.candidate, self.hits, self.stable = None, 0, "uncertain"


# ======================================================================================
# Zero-shot CLIP (default when models/clip_image.onnx exists)
# ======================================================================================
CLIP_IMAGE = Path(__file__).parent / "models" / "clip_image.onnx"
CLIP_TEXT = Path(__file__).parent / "models" / "clip_text.json"
CLIP_MEAN = (0.48145466, 0.4578275, 0.40821073)
CLIP_STD = (0.26862954, 0.26130258, 0.27577711)
CLIP_SCORE_MIN = 0.6           # used only by the offline scorer's 'below threshold' count
# Decision on p(outer): calibrated on 257 desk photos (framing_test), then checked once on the
# separate 40-photo holdout (40/40). Between the two cut-offs -> 'uncertain' (no guess).
CLIP_OUTER_AT = 0.25
CLIP_NONE_BELOW = 0.15
CLIP_EVERY_S = 1.5             # CLIP is heavier: classify at most every 1.5 s, reuse in between


class ClipClothing:
    """Zero-shot: image embedding vs. precomputed text embeddings of clothing descriptions.

    No training on our photos, so no colour/sleeve shortcuts learned from them. Same interface
    as MobileNetClothing: scores(crop) -> [none, outer]; predict(frame); reset(); backend.
    """

    def __init__(self, image_model: Path = CLIP_IMAGE, text_file: Path = CLIP_TEXT):
        import json
        import cv2
        import numpy as np
        import onnxruntime as ort
        self.cv2, self.np = cv2, np
        with open(text_file) as f:
            meta = json.load(f)
        self.scale = float(meta["logit_scale"])
        self.text = np.array([p["embedding"] for p in meta["prompts"]], np.float32)
        self.prompt_label = np.array([LABELS.index(p["label"]) for p in meta["prompts"]])
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self.sess = ort.InferenceSession(str(image_model), opts, providers=["CPUExecutionProvider"])
        self.backend = "CLIP ViT-B/32 zero-shot (onnxruntime int8)"
        self.mean, self.std = np.array(CLIP_MEAN, np.float32), np.array(CLIP_STD, np.float32)
        self.candidate, self.hits, self.stable = None, 0, "uncertain"
        self.last_ms, self.last_at, self.last_score = 0.0, None, None

    def blob(self, crop_bgr):
        cv2, np = self.cv2, self.np
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        size = (224, int(round(224 * h / w))) if w <= h else (int(round(224 * w / h)), 224)
        rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_CUBIC)
        left, top = (size[0] - 224) // 2, (size[1] - 224) // 2
        x = rgb[top:top + 224, left:left + 224].astype(np.float32) / 255.0
        return np.ascontiguousarray(((x - self.mean) / self.std).transpose(2, 0, 1)[None])

    def scores(self, crop_bgr):
        """[p(none), p(outer)]: softmax over all prompts, summed per label."""
        np = self.np
        e = self.sess.run(None, {"pixel_values": self.blob(crop_bgr)})[0][0]
        z = self.scale * (self.text @ e)
        p = np.exp(z - z.max())
        p /= p.sum()
        return np.array([p[self.prompt_label == i].sum() for i in range(len(LABELS))])

    def predict(self, frame):
        now = time.monotonic()
        if self.last_at is not None and now - self.last_at < CLIP_EVERY_S:
            return self.stable, self.last_score, self.last_ms          # reuse: not every frame
        s = self.scores(torso_crop(frame))
        p_outer = float(s[LABELS.index("outer")])
        if p_outer >= CLIP_OUTER_AT:
            label, score = "outer", p_outer
        elif p_outer < CLIP_NONE_BELOW:
            label, score = "none", 1.0 - p_outer
        else:
            label, score = "uncertain", p_outer
        self.hits = self.hits + 1 if label == self.candidate else 1
        self.candidate = label
        if label != "uncertain" and self.hits >= 2:                    # 2 x 1.5 s agreeing
            self.stable = label
        self.last_ms, self.last_at, self.last_score = (time.monotonic() - now) * 1000, now, score
        return self.stable, score, self.last_ms

    def reset(self):
        self.candidate, self.hits, self.stable = None, 0, "uncertain"
        self.last_at = None


def ClothingClassifier():
    """CLIP zero-shot when its files are present; otherwise the trained MobileNet head."""
    if CLIP_IMAGE.exists() and CLIP_TEXT.exists():
        return ClipClothing()
    return MobileNetClothing()
