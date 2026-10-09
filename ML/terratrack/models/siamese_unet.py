"""Siamese ResNet50 + U-Net Change Detection Model."""

from typing import Dict, List, Optional
import torch
import torch.nn as nn

from .resnet_encoder import ResNet50Encoder
from .unet_decoder import UNetDecoder


class SiameseResNetUNet(nn.Module):
    """Siamese ResNet50 + Difference Fusion + U-Net Decoder.
    
    1. Both T1 and T2 pass through the EXACT SAME shared ResNet50 encoder.
    2. At each stage i in [0..4]: Difference D_i = |F_i(T1) - F_i(T2)|
    3. Multi-scale differences feed progressively into U-Net Decoder with skip connections.
    4. Outputs raw logits of shape [B, 1, H, W].
    """
    def __init__(
        self,
        pretrained: bool = True,
        encoder_checkpoint: Optional[str] = None,
        input_channels: int = 3,
        num_classes: int = 1,
        fusion_mode: str = "abs_diff",
    ):
        super().__init__()
        self.fusion_mode = fusion_mode
        self.encoder = ResNet50Encoder(
            pretrained=pretrained,
            checkpoint_path=encoder_checkpoint,
            input_channels=input_channels,
        )
        self.decoder = UNetDecoder(num_classes=num_classes)

    def extract_and_fuse(self, t1: torch.Tensor, t2: torch.Tensor) -> List[torch.Tensor]:
        # Both images pass through the exact same shared encoder instance
        feats_t1 = self.encoder(t1)
        feats_t2 = self.encoder(t2)

        if self.fusion_mode == "abs_diff":
            diff_feats = [torch.abs(f1 - f2) for f1, f2 in zip(feats_t1, feats_t2)]
        else:
            raise NotImplementedError(f"Unsupported fusion mode: {self.fusion_mode}")

        return diff_feats

    def forward(self, t1: torch.Tensor, t2: torch.Tensor) -> torch.Tensor:
        """Forward pass.
        
        Args:
            t1: [B, C, H, W]
            t2: [B, C, H, W]
        Returns:
            logits: [B, 1, H, W]
        """
        diff_feats = self.extract_and_fuse(t1, t2)
        logits = self.decoder(diff_feats, target_size=t1.shape)
        return logits

