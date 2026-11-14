"""Local clothing inference. Scores are uncalibrated; threshold is provisional."""
from pathlib import Path
import time

class ClothingClassifier:
    def __init__(self):
        import torch
        import numpy as np
        from PIL import Image
        self.torch, self.np, self.Image = torch, np, Image
        torch.set_num_threads(2)
        self.model = torch.jit.load(str(Path(__file__).parent/'models/clothing.ts'), map_location='cpu').eval()
        self.candidate, self.hits = None, 0

    def predict(self, frame):
        began = time.monotonic()
        h,w = frame.shape[:2]
        crop = frame[int(.38*h):int(.90*h),int(.20*w):int(.80*w)]
        im = self.Image.fromarray(crop[:,:,::-1])
        w,h = im.size
        size = (256, int(256*h/w)) if w <= h else (int(256*w/h),256)
        im = im.resize(size, self.Image.Resampling.BILINEAR)
        left,top = round((size[0]-224)/2),round((size[1]-224)/2)
        im = im.crop((left,top,left+224,top+224))
        a = self.np.asarray(im,dtype=self.np.float32).copy()/255
        x = self.torch.from_numpy(a).permute(2,0,1)
        x = (x-self.torch.tensor([.485,.456,.406])[:,None,None])/self.torch.tensor([.229,.224,.225])[:,None,None]
        with self.torch.inference_mode():
            scores = self.model(x.unsqueeze(0)).softmax(1)[0]
        score,index = scores.max(0)
        score = float(score)
        label = ('none','outer')[int(index)] if score >= .8 else 'uncertain'
        self.hits = self.hits+1 if label == self.candidate else 1
        self.candidate = label
        return (label if self.hits >= 3 else 'uncertain'), score, (time.monotonic()-began)*1000

    def reset(self):
        self.candidate, self.hits = None, 0
