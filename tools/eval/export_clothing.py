"""Export trained classifier to TorchScript for the UNO Q."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
import torch
from torch import nn
from torchvision.models import mobilenet_v3_small

class Model(nn.Module):
    def __init__(self, checkpoint):
        super().__init__()
        self.backbone = mobilenet_v3_small(weights=None)
        self.backbone.classifier = nn.Identity()
        self.backbone.load_state_dict(checkpoint['backbone'])
        self.head = nn.Linear(len(checkpoint['mean']), 2)
        self.head.load_state_dict(checkpoint['head'])
        self.register_buffer('mean', checkpoint['mean'])
        self.register_buffer('std', checkpoint['std'])
    def forward(self, x):
        return self.head((self.backbone(x)-self.mean)/self.std)

if __name__ == '__main__':
    torch.set_num_threads(2)
    checkpoint = torch.load(ROOT/'tools/eval/data/desk/transfer_model/model.pt', map_location='cpu', weights_only=True)
    assert checkpoint['labels'] == ['none', 'outer']
    model = Model(checkpoint).eval()
    sample = torch.randn(1,3,224,224)
    exported = torch.jit.trace(model, sample)
    torch.testing.assert_close(model(sample), exported(sample))
    path = ROOT/'device/python/models/clothing.ts'
    path.parent.mkdir(exist_ok=True)
    exported.save(str(path))
    print('Exported and verified:', path)
