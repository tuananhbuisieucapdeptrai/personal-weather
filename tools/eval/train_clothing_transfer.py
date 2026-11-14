"""Frozen ImageNet MobileNetV3 features plus a trained clothing classification head.

Uses all prepared training images; fixed settings, no tuning against holdout.
First run downloads pretrained weights. Images remain local.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '.venv/Lib/site-packages'))
import torch
from torch import nn
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights
from PIL import Image

ROOT = Path(__file__).resolve().parent / 'data/desk'
LABELS = ['none', 'outer']


def main():
    torch.manual_seed(23)
    torch.set_num_threads(4)
    weights = MobileNet_V3_Small_Weights.DEFAULT
    print('Loading pretrained MobileNetV3 Small (first run downloads weights)...', flush=True)
    backbone = mobilenet_v3_small(weights=weights).eval()
    backbone.classifier = nn.Identity()
    transform = weights.transforms()
    def load(paths):
        features = []
        for i in range(0, len(paths), 16):
            batch = []
            for p in paths[i:i+16]:
                with Image.open(p) as image:
                    batch.append(transform(image.convert('RGB')))
            with torch.inference_mode():
                features.append(backbone(torch.stack(batch)))
            print(f'Extracted {min(i+16,len(paths))}/{len(paths)}', flush=True)
        return torch.cat(features).clone()
    train = sorted((ROOT / 'prepared_train').glob('*/*.jpg'))
    test = sorted((ROOT / 'holdout_top4/none').glob('*.jpg')) + sorted((ROOT / 'holdout_jacket4/outer').glob('*.jpg'))
    if not train or not test:
        raise RuntimeError('Prepared training and separate holdout images are required')
    x = load(train)
    y = torch.tensor([LABELS.index(p.parent.name) for p in train])
    mean, std = x.mean(0), x.std(0).clamp_min(.05)
    x = (x-mean)/std
    head = nn.Linear(x.shape[1], 2)
    optimizer = torch.optim.AdamW(head.parameters(), lr=.01, weight_decay=.1)
    for epoch in range(100):
        optimizer.zero_grad()
        loss = nn.functional.cross_entropy(head(x), y)
        loss.backward()
        optimizer.step()
        if (epoch+1) % 20 == 0:
            print(f'Epoch {epoch+1}/100; training loss {loss.item():.4f}', flush=True)
    out = ROOT / 'transfer_model'
    out.mkdir(exist_ok=True)
    torch.save({'backbone':backbone.state_dict(), 'head':head.state_dict(),
                'mean':mean, 'std':std, 'labels':LABELS, 'weights':str(weights)}, out/'model.pt')
    # Evaluate only after training finishes; no holdout-driven model selection.
    xt = load(test)
    with torch.no_grad():
        predictions = head((xt-mean)/std).argmax(1).tolist()
    matrix = [[0,0],[0,0]]
    with (out/'predictions.csv').open('w',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['filename','truth','prediction'])
        for p,pred in zip(test,predictions):
            truth = LABELS.index(p.parent.name)
            matrix[truth][pred] += 1
            writer.writerow([p.name,LABELS[truth],LABELS[pred]])
    report = {'training_images':len(train),'test_images':len(test),'labels':LABELS,
              'confusion_matrix':matrix,'accuracy':sum(matrix[i][i] for i in range(2))/len(test),
              'note':'Small two-person holdout; not population-wide accuracy. No confidence threshold calibrated.'}
    (out/'results.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2), flush=True)


if __name__ == '__main__':
    main()
