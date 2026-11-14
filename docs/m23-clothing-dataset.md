# M2.3: public training data, small local test

Status: 72 `outer` and 100 `none` candidates downloaded from Fashionpedia. A contact-sheet review excluded 10 obvious `outer` and 27 `none` errors. A lightweight local ridge baseline trained on 108 remaining images and scored **14/27 (51.9%)** on a seeded, held-out public-image split (outer 8/12; none 6/15). The baseline is saved in gitignored `tools/eval/data/fashionpedia/baseline_model.npz`, with per-image results in `baseline_predictions.csv`. This result is too weak to deploy; no desk-camera holdout or transfer-learning model has been completed. Production `vision.py` still reports `clothing="uncertain"`.

## 1. Prepare public training crops on your laptop

Fashionpedia identifies garment boxes. This deliberately narrow mapping uses **jacket/coat/cardigan = outer** and **shirt/blouse/T-shirt/top/sweatshirt = none**. Sweaters, vests, dresses and photos with multiple upper garments are excluded because a garment category alone does not tell us whether an *extra* layer is worn. Review the images and remove ambiguous or wrongly cropped examples. Public garment photos differ from the desk camera; this is a quick baseline, not proof of real-world accuracy.

```powershell
& "C:\Program Files\KiCad\10.0\bin\python.exe" -u tools/eval/prepare_fashionpedia.py --per-class 100
```

The script uses the already installed `datasets` and Pillow packages from `.venv` while running through the working KiCad Python interpreter. It streams the smaller Fashionpedia `val` source split by default (about 1,158 images); this is a *source name*, not our model's validation or held-out split. It saves up to 100 per class as 160x160 garment crops and a provenance manifest under the gitignored `tools/eval/data/fashionpedia/`. If insufficient, use `--source-split train`, which is substantially larger. Streaming may still download substantial data, depending on file layout. Reduce `--per-class` to 50 if needed. **Inspect every selected crop and remove unrelated body regions, ambiguous fabric, and incorrect labels.** The initial 20-image pilot already contained bad examples. After removal, retain only manifest rows whose filenames still exist; rerunning the script regenerates the manifest and may recreate rejected images. Read the dataset's image terms before using or uploading it; Fashionpedia does not own the original images. Source: https://fashionpedia.github.io/home/data_license.html ; dataset: https://huggingface.co/datasets/detection-datasets/fashionpedia

## 2. Reserve a small desk-camera test

Do **not** add desk photos to training for the first evaluation. Stop the vision app so the UNO Q camera is free, copy `tools/eval/capture_clothing.py` to the board, and obtain each participant's explicit consent. Then, on the board:

```bash
python3 capture_clothing.py --session desk_holdout --label outer --person p1 --count 8
python3 capture_clothing.py --session desk_holdout --label none --person p1 --count 8
```

Repeat for p2 if available. The images remain at `~/pw-clothing-data/desk_holdout/{outer,none}` on the board; the script never uploads them. Use actual add/remove-layer conditions with the same camera framing as the intended demo. Inspect the crops; remove faces, bad framing and wrong labels. These 16–32 frames give a small but honest desk-domain test, not a reliable population-wide accuracy estimate. Empty-chair frames belong to the presence test, not the clothing `none` class. Keep identities and images out of Git; delete photos after the event.

## 3. Train and report

The initial local baseline can be reproduced with `& "C:\Program Files\KiCad\10.0\bin\python.exe" tools/eval/train_clothing_baseline.py`. Its exclusions are a first-pass contact-sheet review and require closer inspection before any external training upload. Its public holdout accuracy is only 51.9%, near chance. The `.npz` is a diagnostic baseline, not a UNO Q deployment artifact. Do not interpret a random Fashionpedia split as desk-camera accuracy.

Create an Edge Impulse image classification project with labels `outer` and `none`. Upload the reviewed **public** crops to training. Upload the **entire desk_holdout session** to testing, choosing Test explicitly rather than automatic random split. Train an image input plus transfer-learning classifier and inspect the test confusion matrix. Do not use desk_holdout to choose garments, thresholds or settings; if tuning is necessary, collect a new final holdout. Uploading the desk images would share that consented dataset with Edge Impulse; confirm consent covers that destination. Studio overview: https://docs.edgeimpulse.com/docs

Alternatively, evaluate locally after export without uploading desk images. Make a private `truth,prediction` CSV with one row per held-out image and run `& "C:\Program Files\KiCad\10.0\bin\python.exe" tools/eval/score_clothing.py predictions.csv`. It reports coverage and accuracy with uncertain outcomes counted both ways. Record image counts, class definitions, held-out result, confusion matrix and inference latency in `docs/results.md`. M2.4 then deploys the classifier on UNO Q, adds the live torso crop, stability and `uncertain` threshold. If the local test fails, use the existing manual clothing control as the planned fallback.
