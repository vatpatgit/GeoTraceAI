"""IDA-SiamNet style change-detection network (Interactive- and Dynamic-Aware Siamese Network), in plain PyTorch.

Re-implementation of the design in https://github.com/SUPERMAN123000/IDA-SiamNet (Open-CD/mmcv based) without the mmcv dependency:

* **Interactive backbone** - a weight-shared ResNet processes both dates; after the deeper stages the two feature maps exchange
  information through ``SEFI`` (spatial-exchange attention, stage 2) and ``CEFI`` (channel-exchange attention, stages 3-4).
* **Dynamic-aware head** - per-date multi-scale features are projected, upsampled and fused, then ``FDAF`` aligns the two dates with an
  adaptive (deformable, gated) convolution and a learned flow warp, takes the cross-date differences, and a MixFFN projects them
  to the change logit.

Differences from the reference: ResNet50 (ImageNet weights from the local torch cache) replaces ResNet18 / MiT-b1 because no other
backbone weights are available offline; BatchNorm replaces SyncBN (single GPU); the head predicts one logit (BCE + Dice) instead of two
softmax classes with OHEM; the adaptive convolution uses ``torchvision.ops.deform_conv2d`` instead of a hand-written gather.

``forward(t1, t2)`` returns raw logits ``[B, 1, H, W]``, like ``SiameseResNetUNet``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models import resnet50
from torchvision.ops import deform_conv2d


class CEFI(nn.Module):
    """Channel-exchange feature interaction: each date's channel attention gates the other date's depthwise-separable features."""

    def __init__(self, channel: int, reduction: int = 2):
        super().__init__()
        self.avg_pool, self.max_pool = nn.AdaptiveAvgPool2d(1), nn.AdaptiveMaxPool2d(1)
        self.fc = nn.Sequential(nn.Linear(channel, channel // reduction, bias=False), nn.Mish(inplace=True), nn.Linear(channel // reduction, channel, bias=False), nn.Sigmoid())
        self.depth_conv = nn.Conv2d(channel, channel, 3, 1, 1, groups=channel)
        self.point_conv = nn.Conv2d(channel, channel, 1)

    def _att(self, x):
        b, c = x.shape[:2]
        return self.fc(self.avg_pool(x).view(b, c) + self.max_pool(x).view(b, c)).view(b, c, 1, 1)

    def forward(self, x1, x2):
        y1, y2 = self._att(x1), self._att(x2)
        g1 = self.point_conv(self.depth_conv(x1)) + x1
        g2 = self.point_conv(self.depth_conv(x2)) + x2
        return x1 * y1 + g2 * y1 + g1, x2 * y2 + g1 * y2 + g2


class SEFI(nn.Module):
    """Spatial-exchange feature interaction: spatial attention for date 1 uses its own mean map and date 2's max map (and vice versa)."""

    def __init__(self):
        super().__init__()
        self.conv = nn.Conv2d(2, 1, 7, 1, 3)

    def forward(self, x1, x2):
        a1, a2 = x1.mean(1, keepdim=True), x2.mean(1, keepdim=True)
        m1, m2 = x1.amax(1, keepdim=True), x2.amax(1, keepdim=True)
        return x1 * torch.sigmoid(self.conv(torch.cat([a1, m2], 1))), x2 * torch.sigmoid(self.conv(torch.cat([a2, m1], 1)))


class AdaptiveConv2d(nn.Module):
    """3x3 deformable convolution with zero-initialised offsets (starts as a plain conv) and a channel gate computed from the input."""

    def __init__(self, inc: int, outc: int, k: int = 3, shrink: float = 0.25):
        super().__init__()
        self.k = k
        self.weight = nn.Parameter(torch.empty(outc, inc, k, k))
        nn.init.kaiming_uniform_(self.weight, a=5 ** 0.5)
        self.p_conv = nn.Conv2d(inc, 2 * k * k, 3, padding=1)
        nn.init.zeros_(self.p_conv.weight); nn.init.zeros_(self.p_conv.bias)
        hid = max(int(inc * shrink), 4)
        self.gate = nn.Sequential(nn.AdaptiveAvgPool2d(1), nn.Conv2d(inc, hid, 1), nn.GELU(), nn.Conv2d(hid, outc, 1), nn.Sigmoid())

    def forward(self, x):
        off = self.p_conv(x)
        out = deform_conv2d(x.float(), off.float(), self.weight.float(), padding=self.k // 2).to(x.dtype)
        return self.gate(x) * out


def warp(x: torch.Tensor, flow: torch.Tensor) -> torch.Tensor:
    n, _, h, w = x.shape
    ys = torch.linspace(-1.0, 1.0, h, device=x.device, dtype=x.dtype).view(-1, 1).expand(h, w)
    xs = torch.linspace(-1.0, 1.0, w, device=x.device, dtype=x.dtype).view(1, -1).expand(h, w)
    grid = torch.stack((xs, ys), 2).unsqueeze(0).expand(n, -1, -1, -1)
    norm = torch.tensor([w, h], device=x.device, dtype=x.dtype).view(1, 1, 1, 2)
    return F.grid_sample(x, grid + flow.permute(0, 2, 3, 1).to(x.dtype) / norm, align_corners=True)


class FDAF(nn.Module):
    """Flow dual-alignment fusion: align each date to the other with a learned flow, then take cross-date differences."""

    def __init__(self, c: int):
        super().__init__()
        self.flow_make = nn.Sequential(nn.Conv2d(2 * c, 2 * c, 5, padding=2, groups=2 * c), nn.InstanceNorm2d(2 * c), nn.GELU())
        self.flow_last = nn.Conv2d(2 * c, 4, 1, bias=False)
        self.adaptive = AdaptiveConv2d(c, c)

    def forward(self, x1, x2):
        u1, u2 = self.adaptive(x1), self.adaptive(x2)
        f1, f2 = torch.chunk(self.flow_last(self.flow_make(torch.cat([x1, x2], 1))), 2, 1)
        return torch.cat([warp(u1, f1) - u2, warp(u2, f2) - u1], 1)


class MixFFN(nn.Module):
    def __init__(self, c: int):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(c, c, 1), nn.Conv2d(c, c, 3, padding=1, groups=c), nn.GELU(), nn.Conv2d(c, c, 1))

    def forward(self, x):
        return x + self.net(x)


class IDASiamNet(nn.Module):
    def __init__(self, pretrained_weights: Optional[str] = "auto", channels: int = 128, interaction: bool = True, dropout: float = 0.1):
        super().__init__()
        base = resnet50(weights=None)
        if pretrained_weights:
            p = Path.home() / ".cache/torch/hub/checkpoints/resnet50-11ad3fa6.pth" if pretrained_weights == "auto" else Path(pretrained_weights)
            if p.is_file():
                base.load_state_dict(torch.load(p, map_location="cpu"))
        self.stem = nn.Sequential(base.conv1, base.bn1, base.relu, base.maxpool)
        self.layers = nn.ModuleList([base.layer1, base.layer2, base.layer3, base.layer4])
        chans = (256, 512, 1024, 2048)
        self.interact = nn.ModuleList([nn.Identity(), SEFI(), CEFI(chans[2]), CEFI(chans[3])]) if interaction else None
        self.projs = nn.ModuleList([nn.Sequential(nn.Conv2d(c, channels, 1, bias=False), nn.BatchNorm2d(channels), nn.ReLU(inplace=True)) for c in chans])
        self.fusion = nn.Sequential(nn.Conv2d(channels * 4, channels // 2, 1, bias=False), nn.BatchNorm2d(channels // 2))
        self.fdaf = FDAF(channels // 2)
        self.ffn = MixFFN(channels)
        self.drop = nn.Dropout2d(dropout)
        self.cls = nn.Conv2d(channels, 1, 1)

    def _encode(self, x1, x2):
        x1, x2 = self.stem(x1), self.stem(x2)
        f1, f2 = [], []
        for i, layer in enumerate(self.layers):
            x1, x2 = layer(x1), layer(x2)
            if self.interact is not None and i > 0:
                x1, x2 = self.interact[i](x1, x2)
            f1.append(x1); f2.append(x2)
        return f1, f2

    def _fuse(self, feats):
        size = feats[0].shape[2:]
        outs = [F.interpolate(p(f), size=size, mode="bilinear", align_corners=False) for p, f in zip(self.projs, feats)]
        return self.fusion(torch.cat(outs, 1))

    def forward(self, t1: torch.Tensor, t2: torch.Tensor) -> torch.Tensor:
        f1, f2 = self._encode(t1, t2)
        out = self.ffn(self.fdaf(self._fuse(f1), self._fuse(f2)))
        out = self.cls(self.drop(out))
        return F.interpolate(out, size=t1.shape[2:], mode="bilinear", align_corners=False)
