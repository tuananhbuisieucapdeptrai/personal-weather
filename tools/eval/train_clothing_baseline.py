"""Train a small, reproducible public-photo baseline; desk-camera evaluation is separate.

Requires Pillow and NumPy. Output model is a NumPy .npz file, not a deployed model.
"""
import argparse
import csv
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

ROOT = Path('tools/eval/data/fashionpedia')
# Contact-sheet review: wrong body region, ambiguous garment, or visible added layer
# in the 'none' category. Exclusions are kept by image ID across re-downloads.
REJECT_OUTER = {9104, 10572, 11408, 11720, 12153, 12809, 13390, 17994, 19223, 23337}
REJECT_NONE = {8337, 8610, 8671, 8976, 9048, 9174, 9347, 9390, 9425, 9465,
               9507, 9810, 10011, 10216, 10512, 10518, 10858, 10976, 11171,
               11349, 11446, 11630, 11849, 11856, 11903, 11925, 12054}


def features(path):
    with Image.open(path) as src:
        im = ImageOps.fit(src.convert('RGB'), (32, 32))
    a = np.asarray(im, dtype=np.float32) / 255.0
    # Color plus coarse spatial layout; deliberately simple and CPU friendly.
    color = a.reshape(8, 4, 8, 4, 3).mean(axis=(1, 3)).ravel()
    gray = a.mean(axis=2)
    dx = np.abs(np.diff(gray, axis=1)).reshape(32, 31)
    dy = np.abs(np.diff(gray, axis=0)).reshape(31, 32)
    edge = np.array([dx.mean(), dy.mean(), dx.std(), dy.std()], dtype=np.float32)
    return np.concatenate((color, edge))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=ROOT)
    args = ap.parse_args()
    entries = {'outer': [], 'none': []}
    with (args.root / 'manifest.csv').open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            label = row['label']
            if int(row['image_id']) in (REJECT_OUTER if label == 'outer' else REJECT_NONE):
                continue
            path = args.root / row['filename']
            if path.is_file():
                entries[label].append((row['image_id'], path))
    if min(map(len, entries.values())) < 20:
        raise ValueError(f'Too few reviewed examples: { {k: len(v) for k,v in entries.items()} }')
    rng = np.random.default_rng(23)
    train, test = [], []
    for label in ('outer', 'none'):
        group = entries[label]
        rng.shuffle(group)
        n_test = max(8, round(len(group) * .2))
        test.extend((label, *item) for item in group[:n_test])
        train.extend((label, *item) for item in group[n_test:])
    x = np.stack([features(p) for _, _, p in train])
    y = np.array([int(label == 'outer') for label, _, _ in train], dtype=float)
    mean, std = x.mean(axis=0), x.std(axis=0)
    std[std < .05] = .05
    z = (x - mean) / std
    # Ridge regression, balanced class weights, with an unpenalized intercept.
    z = np.column_stack((z, np.ones(len(z))))
    weights = np.where(y == 1, len(y)/(2*sum(y)), len(y)/(2*(len(y)-sum(y))))
    penalty = np.eye(z.shape[1]) * 30
    penalty[-1, -1] = 0
    coef = np.linalg.solve(z.T @ (weights[:, None] * z) + penalty,
                           z.T @ (weights * y))
    xt = np.stack([features(p) for _, _, p in test])
    scores = np.column_stack(((xt-mean)/std, np.ones(len(xt)))) @ coef
    prediction = np.where(scores >= .5, 'outer', 'none')
    result = args.root / 'baseline_predictions.csv'
    with result.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['image_id', 'truth', 'prediction', 'score_outer'])
        writer.writerows((id_, label, pred, f'{score:.4f}') for
                         (label, id_, _), pred, score in zip(test, prediction, scores))
    model = args.root / 'baseline_model.npz'
    np.savez(model, mean=mean, std=std, coef=coef)
    print('Reviewed counts:', {k:len(v) for k,v in entries.items()})
    print('Training:', len(train), 'Public holdout:', len(test))
    print('Public holdout accuracy:', f'{sum(p == t for p,(t,_,_) in zip(prediction,test))}/{len(test)}')
    print('Model:', model, 'Predictions:', result)


if __name__ == '__main__':
    main()
