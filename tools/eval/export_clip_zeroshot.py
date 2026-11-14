"""Zero-shot clothing model for the UNO Q (laptop-side export).  Owner: Tuan Anh.

Why: the trained MobileNet head (240 photos) learned colour/sleeve shortcuts and failed a
live test. CLIP (OpenAI ViT-B/32) compares an image with text descriptions and needs NO
training data, so it cannot overfit our photos.

What this does (laptop only, once):
  1. Text side: embeds the PROMPTS below with CLIP's text encoder and saves the normalised
     vectors to device/python/models/clip_text.json (the board never runs the text model).
  2. Image side: exports CLIP's vision encoder + projection to ONNX, then 8-bit dynamic
     quantisation -> device/python/models/clip_image.onnx, and checks it still agrees with
     the full-precision model (cosine similarity printed).

The prompts were fixed BEFORE scoring any desk photo; they are not tuned on our data.

    .venv/bin/pip install torch transformers onnx onnxruntime
    .venv/bin/python tools/eval/export_clip_zeroshot.py
"""
from __future__ import annotations

import json
import os

import numpy as np
import torch
from transformers import CLIPModel, CLIPTokenizer

MODEL_ID = "openai/clip-vit-base-patch32"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "device", "python", "models")
PROMPTS = {
    "outer": [
        "a photo of a person wearing a jacket",
        "a photo of a person wearing a coat",
        "a photo of a person wearing a hoodie",
        "a photo of a person wearing a zipped jacket over a shirt",
        "a photo of a person wearing a cardigan over a shirt",
        "a photo of a person wearing a blazer",
    ],
    "none": [
        "a photo of a person wearing a t-shirt",
        "a photo of a person wearing a short-sleeved shirt",
        "a photo of a person wearing a plain shirt",
        "a photo of a person wearing a long-sleeved t-shirt",
        "a photo of a person wearing a polo shirt",
        "a photo of a person wearing a tank top",
    ],
}


class VisionEmbed(torch.nn.Module):
    def __init__(self, clip):
        super().__init__()
        self.vision, self.proj = clip.vision_model, clip.visual_projection

    def forward(self, pixel_values):
        e = self.proj(self.vision(pixel_values=pixel_values).pooler_output)
        return e / e.norm(dim=-1, keepdim=True)


def main():
    clip = CLIPModel.from_pretrained(MODEL_ID).eval()
    tok = CLIPTokenizer.from_pretrained(MODEL_ID)
    entries = []
    with torch.inference_mode():
        for label, prompts in PROMPTS.items():
            pooled = clip.text_model(**tok(prompts, padding=True, return_tensors="pt")).pooler_output
            t = clip.text_projection(pooled)
            t = t / t.norm(dim=-1, keepdim=True)
            entries += [{"label": label, "prompt": p, "embedding": [round(float(x), 6) for x in v]}
                        for p, v in zip(prompts, t)]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "clip_text.json"), "w") as f:
        json.dump({"model": MODEL_ID, "logit_scale": float(clip.logit_scale.exp()), "prompts": entries}, f)

    fp32 = os.path.join(OUT, "clip_image_fp32.onnx")
    final = os.path.join(OUT, "clip_image.onnx")
    model = VisionEmbed(clip).eval()
    torch.onnx.export(model, torch.zeros(1, 3, 224, 224), fp32, input_names=["pixel_values"],
                      output_names=["image_embeds"], opset_version=17, dynamo=False)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    quantize_dynamic(fp32, final, weight_type=QuantType.QInt8)

    import onnxruntime as ort
    s32 = ort.InferenceSession(fp32, providers=["CPUExecutionProvider"])
    s8 = ort.InferenceSession(final, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(0)
    sims = []
    for _ in range(6):
        x = rng.normal(0, 1, (1, 3, 224, 224)).astype(np.float32)
        a = s32.run(None, {"pixel_values": x})[0][0]
        b = s8.run(None, {"pixel_values": x})[0][0]
        sims.append(float(a @ b / np.linalg.norm(a) / np.linalg.norm(b)))
    os.remove(fp32)
    print(f"text prompts: {len(entries)} -> models/clip_text.json")
    print(f"image model: models/clip_image.onnx ({os.path.getsize(final) / 1e6:.0f} MB, int8); "
          f"cosine(fp32, int8) min {min(sims):.4f}")


if __name__ == "__main__":
    main()
