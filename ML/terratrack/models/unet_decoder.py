"""U-Net Decoder for Progressive Multi-Scale Difference Reconstruction."""

from typing import List
import torch
import torch.nn as nn
import torch.nn.functional as F


class ConvBlock(nn.Module):
    """Double 3x3 Conv + BatchNorm + ReLU block."""
    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class DecoderStage(nn.Module):
    """Upsampling + concatenation with skip feature + convolution."""
    def __init__(self, in_channels: int, skip_channels: int, out_channels: int):
        super().__init__()
        self.conv = ConvBlock(in_channels + skip_channels, out_channels)

    def forward(self, x: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        x_up = F.interpolate(x, size=skip.shape[2:], mode="bilinear", align_corners=False)
        x_cat = torch.cat([x_up, skip], dim=1)
        return self.conv(x_cat)


class UNetDecoder(nn.Module):
    """Progressive U-Net Decoder accepting multi-scale difference features.
    
    Inputs:
        diff_features:
            diff0: [B, 64, H/2, W/2]
            diff1: [B, 256, H/4, W/4]
            diff2: [B, 512, H/8, W/8]
            diff3: [B, 1024, H/16, W/16]
            diff4: [B, 2048, H/32, W/32]
    Output:
        change_logits: [B, 1, H, W]
    """
    def __init__(self, num_classes: int = 1):
        super().__init__()
        # stage 4 -> stage 3: 2048 up + 1024 -> 512
        self.dec4 = DecoderStage(in_channels=2048, skip_channels=1024, out_channels=512)
        # stage 3 -> stage 2: 512 up + 512 -> 256
        self.dec3 = DecoderStage(in_channels=512, skip_channels=512, out_channels=256)
        # stage 2 -> stage 1: 256 up + 256 -> 128
        self.dec2 = DecoderStage(in_channels=256, skip_channels=256, out_channels=128)
        # stage 1 -> stage 0: 128 up + 64 -> 64
        self.dec1 = DecoderStage(in_channels=128, skip_channels=64, out_channels=64)
        
        # final upsampling stage: 64 up to full resolution (H, W) -> 32 -> 1 logits
        self.final_conv = nn.Sequential(
            nn.Conv2d(64, 32, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.Conv2d(32, num_classes, kernel_size=1),
        )

    def forward(self, diff_feats: List[torch.Tensor], target_size: torch.Size) -> torch.Tensor:
        d0, d1, d2, d3, d4 = diff_feats

        x = self.dec4(d4, d3)  # [B, 512, H/16, W/16]
        x = self.dec3(x, d2)   # [B, 256, H/8, W/8]
        x = self.dec2(x, d1)   # [B, 128, H/4, W/4]
        x = self.dec1(x, d0)   # [B, 64, H/2, W/2]

        x = F.interpolate(x, size=target_size[2:], mode="bilinear", align_corners=False)
        logits = self.final_conv(x)  # [B, 1, H, W]
        return logits

