"""Convert Minh's clothing model (TorchScript) to ONNX for OpenCV DNN on the UNO Q.  Laptop only.

Why: PyTorch on the board fails to import (libtorch_cpu.so: undefined symbol sbgemm_),
but App Lab already ships OpenCV 4.13, whose DNN module runs ONNX. Same weights, no
retraining, no PyTorch on the board.

    python3 -m venv .venv && .venv/bin/pip install torch onnx onnxscript opencv-python-headless
    .venv/bin/python tools/eval/export_clothing_onnx.py

Writes device/python/models/clothing.onnx and checks that OpenCV's output matches
TorchScript on random and structured inputs (max |softmax difference| printed).
"""
from __future__ import annotations

import os

import cv2
import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "..", "..", "device", "python", "models")
TS, ONNX = os.path.join(MODELS, "clothing.ts"), os.path.join(MODELS, "clothing.onnx")


def softmax(x):
    e = np.exp(x - x.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def main():
    model = torch.jit.load(TS, map_location="cpu").eval()
    dummy = torch.zeros(1, 3, 224, 224)
    torch.onnx.export(model, dummy, ONNX, input_names=["image"], output_names=["logits"],
                      opset_version=13, dynamo=False)
    net = cv2.dnn.readNetFromONNX(ONNX)
    rng = np.random.default_rng(0)
    inputs = [rng.normal(0, 1, (1, 3, 224, 224)).astype(np.float32) for _ in range(8)]
    for v in (-2.0, 0.0, 2.0):
        inputs.append(np.full((1, 3, 224, 224), v, np.float32))
    ramp = np.linspace(-2, 2, 224, dtype=np.float32)
    inputs.append(np.broadcast_to(ramp, (1, 3, 224, 224)).copy())
    worst, agree = 0.0, 0
    for x in inputs:
        with torch.inference_mode():
            ref = softmax(model(torch.from_numpy(x)).numpy())
        net.setInput(x)
        got = softmax(net.forward())
        worst = max(worst, float(np.abs(ref - got).max()))
        agree += int(ref.argmax() == got.argmax())
    print(f"wrote {os.path.relpath(ONNX)} ({os.path.getsize(ONNX) / 1e6:.1f} MB)")
    print(f"OpenCV DNN vs TorchScript on {len(inputs)} inputs: max |softmax diff| = {worst:.2e}, "
          f"same class {agree}/{len(inputs)}")
    if worst > 1e-3 or agree != len(inputs):
        raise SystemExit("MISMATCH: do not deploy")


if __name__ == "__main__":
    main()
