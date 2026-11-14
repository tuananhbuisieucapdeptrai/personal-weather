"""Select balanced Fashionpedia garment crops for M2.3 public-data training.

Requires: pip install datasets pillow. The selected images and provenance stay
under tools/eval/data (gitignored). Review them before any training/upload.
"""
import argparse
import csv
from pathlib import Path
import sys

OUTER = {"jacket", "coat", "cardigan"}
NONE = {"shirt, blouse", "top, t-shirt, sweatshirt"}
UPPER = OUTER | NONE | {"sweater", "vest", "cape", "dress", "jumpsuit"}


def eligible(objects, names, width, height):
    """Only one clear upper garment; ambiguous or overlapping garments are skipped."""
    garments = [(names[c], box) for c, box in zip(objects["category"], objects["bbox"])
                if names[c] in UPPER]
    if len(garments) != 1:
        return None
    name, box = garments[0]
    label = "outer" if name in OUTER else "none" if name in NONE else None
    if not label:
        return None
    x1, y1, x2, y2 = box
    if x2-x1 < 70 or y2-y1 < 70 or (x2-x1)*(y2-y1) < .025*width*height:
        return None
    return label, name, box


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-class", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("tools/eval/data/fashionpedia"))
    parser.add_argument("--max-scan", type=int, default=15000)
    parser.add_argument("--source-split", choices=("val", "train"), default="val",
                        help="Fashionpedia val is much smaller; desk session remains the test")
    args = parser.parse_args()
    if args.per_class < 1 or args.max_scan < 1:
        parser.error("counts must be positive")
    try:
        from datasets import load_dataset
    except ModuleNotFoundError:
        # The Windows venv launcher may fail silently in App Lab's shell, while
        # its packages remain usable by the working KiCad Python executable.
        site = Path(__file__).resolve().parents[2] / ".venv" / "Lib" / "site-packages"
        if not site.is_dir():
            raise
        sys.path.insert(0, str(site))
        from datasets import load_dataset
    from PIL import ImageOps

    print("Connecting to Fashionpedia on Hugging Face; the first download can take time...", flush=True)
    dataset = load_dataset("detection-datasets/fashionpedia", split=args.source_split, streaming=True)
    print("Dataset opened. Scanning annotations and downloading selected images...", flush=True)
    object_features = dataset.features["objects"]
    category_feature = (object_features.feature["category"]
                        if hasattr(object_features, "feature") else object_features["category"])
    # datasets 5.x exposes a Sequence-of-records as a dict of Sequence fields.
    if hasattr(category_feature, "feature"):
        category_feature = category_feature.feature
    names = category_feature.names
    counts = {"outer": 0, "none": 0}
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = args.output / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["source", "image_id", "category", "label", "filename"])
        for index, sample in enumerate(dataset):
            if index >= args.max_scan or min(counts.values()) >= args.per_class:
                break
            if index and index % 500 == 0:
                print(f"Scanned {index} images; selected {counts}", flush=True)
            result = eligible(sample["objects"], names, sample["width"], sample["height"])
            if not result:
                continue
            label, name, (x1, y1, x2, y2) = result
            if counts[label] >= args.per_class:
                continue
            image = sample["image"].convert("RGB")
            # Crop only the annotated garment, avoiding faces and most background.
            box = (max(0, int(x1)), max(0, int(y1)),
                   min(image.width, int(x2)), min(image.height, int(y2)))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            crop = ImageOps.fit(image.crop(box), (160, 160))
            dest = args.output / "training" / label
            dest.mkdir(parents=True, exist_ok=True)
            name_out = f"fashionpedia_{sample['image_id']}_{label}.jpg"
            crop.save(dest / name_out, quality=85)
            writer.writerow([f"Fashionpedia/{args.source_split}", sample["image_id"], name, label,
                             f"training/{label}/{name_out}"])
            counts[label] += 1
            if sum(counts.values()) % 20 == 0:
                print(f"Scanned {index+1}; selected {counts}", flush=True)
    print(f"Selected {counts}; inspect {args.output / 'training'} and {manifest}")
    if min(counts.values()) < args.per_class:
        print("Target not reached; increase --max-scan or lower --per-class")


if __name__ == "__main__":
    main()
