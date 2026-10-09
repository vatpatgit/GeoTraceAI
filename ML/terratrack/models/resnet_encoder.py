"""ResNet50 Multi-Scale Spatial Feature Extractor."""

from typing import List, Optional
import torch
import torch.nn as nn
from torchvision.models import resnet50, ResNet50_Weights


class ResNet50Encoder(nn.Module):
    """ResNet50 spatial feature extractor returning multi-scale feature maps.
    
    Stages:
        Stage 0 (initial conv + bn + relu): [B, 64, H/2, W/2]
        Stage 1 (layer1 after maxpool):     [B, 256, H/4, W/4]
        Stage 2 (layer2):                   [B, 512, H/8, W/8]
        Stage 3 (layer3):                   [B, 1024, H/16, W/16]
        Stage 4 (layer4):                   [B, 2048, H/32, W/32]
        
    For an input of [B, 3, 256, 256]:
        Stage 0: [B, 64, 128, 128]
        Stage 1: [B, 256, 64, 64]
        Stage 2: [B, 512, 32, 32]
        Stage 3: [B, 1024, 16, 16]
        Stage 4: [B, 2048, 8, 8]
    """
    def __init__(
        self,
        pretrained: bool = True,
        checkpoint_path: Optional[str] = None,
        input_channels: int = 3,
    ):
        super().__init__()
        weights = ResNet50_Weights.DEFAULT if pretrained and checkpoint_path is None else None
        base = resnet50(weights=weights)

        # Configurable input channels (default 3 for RGB)
        if input_channels != 3:
            orig_conv = base.conv1
            self.conv1 = nn.Conv2d(
                input_channels,
                orig_conv.out_channels,
                kernel_size=orig_conv.kernel_size,
                stride=orig_conv.stride,
                padding=orig_conv.padding,
                bias=orig_conv.bias is not None,
            )
            # Replicate or average pretrained weights if available
            with torch.no_grad():
                if orig_conv.weight is not None:
                    mean_weight = orig_conv.weight.mean(dim=1, keepdim=True)
                    self.conv1.weight.copy_(mean_weight.repeat(1, input_channels, 1, 1))
        else:
            self.conv1 = base.conv1

        self.bn1 = base.bn1
        self.relu = base.relu
        self.maxpool = base.maxpool

        self.layer1 = base.layer1
        self.layer2 = base.layer2
        self.layer3 = base.layer3
        self.layer4 = base.layer4

        # Custom checkpoint loading (e.g. EuroSAT pretrained ResNet50)
        if checkpoint_path is not None:
            self._load_custom_checkpoint(checkpoint_path)

    def _load_custom_checkpoint(self, checkpoint_path: str):
        print(f"Loading custom encoder checkpoint from: {checkpoint_path}")
        state = torch.load(checkpoint_path, map_location="cpu")
        if "model_state_dict" in state:
            state = state["model_state_dict"]
        elif "state_dict" in state:
            state = state["state_dict"]
            
        # Filter matching keys and ignore fc / avgpool
        model_dict = self.state_dict()
        filtered = {k: v for k, v in state.items() if k in model_dict and v.shape == model_dict[k].shape}
        model_dict.update(filtered)
        self.load_state_dict(model_dict)
        print(f"Loaded {len(filtered)} / {len(model_dict)} matching parameters into ResNet50 encoder.")

    def forward(self, x: torch.Tensor) -> List[torch.Tensor]:
        """Extract multi-scale features: [stage0, stage1, stage2, stage3, stage4]."""
        x0 = self.relu(self.bn1(self.conv1(x)))  # [B, 64, H/2, W/2]
        x1 = self.layer1(self.maxpool(x0))      # [B, 256, H/4, W/4]
        x2 = self.layer2(x1)                     # [B, 512, H/8, W/8]
        x3 = self.layer3(x2)                     # [B, 1024, H/16, W/16]
        x4 = self.layer4(x3)                     # [B, 2048, H/32, W/32]
        return [x0, x1, x2, x3, x4]

