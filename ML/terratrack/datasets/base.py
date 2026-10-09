"""Common dataset definitions, transforms, and metadata container."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
import random
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset
import torchvision.transforms.functional as TF


@dataclass
class ChangeSample:
    dataset: str
    id: str
    image_t1: torch.Tensor      # [C, H, W], float32 in [0, 1] (or normalized)
    image_t2: torch.Tensor      # [C, H, W], float32 in [0, 1] (or normalized)
    mask: torch.Tensor          # [1, H, W], float32 {0.0, 1.0}
    metadata: Dict[str, Any]


class PairedTransform:
    """Applies identical spatial transformations to T1, T2, and binary mask.
    
    Ensures spatial correspondence is strictly maintained across all inputs.
    """
    def __init__(
        self,
        target_size: Tuple[int, int] = (256, 256),
        is_train: bool = True,
        hflip_prob: float = 0.5,
        vflip_prob: float = 0.5,
        rotate_degrees: float = 15.0,
        normalize_mean: Tuple[float, float, float] = (0.485, 0.456, 0.406),
        normalize_std: Tuple[float, float, float] = (0.229, 0.224, 0.225),
    ):
        self.target_size = target_size
        self.is_train = is_train
        self.hflip_prob = hflip_prob
        self.vflip_prob = vflip_prob
        self.rotate_degrees = rotate_degrees
        self.normalize_mean = normalize_mean
        self.normalize_std = normalize_std

    def __call__(
        self, img_t1: Image.Image, img_t2: Image.Image, mask: np.ndarray
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        # Resize all to target size
        # Bilinear for images, Nearest for binary change mask
        img_t1 = TF.resize(img_t1, self.target_size, interpolation=TF.InterpolationMode.BILINEAR)
        img_t2 = TF.resize(img_t2, self.target_size, interpolation=TF.InterpolationMode.BILINEAR)
        
        # Convert mask to PIL Image for synchronized geometric transforms
        mask_pil = Image.fromarray((mask * 255).astype(np.uint8))
        mask_pil = TF.resize(mask_pil, self.target_size, interpolation=TF.InterpolationMode.NEAREST)

        if self.is_train:
            # Synchronized Horizontal Flip
            if random.random() < self.hflip_prob:
                img_t1 = TF.hflip(img_t1)
                img_t2 = TF.hflip(img_t2)
                mask_pil = TF.hflip(mask_pil)

            # Synchronized Vertical Flip
            if random.random() < self.vflip_prob:
                img_t1 = TF.vflip(img_t1)
                img_t2 = TF.vflip(img_t2)
                mask_pil = TF.vflip(mask_pil)

            # Synchronized Random Rotation
            if self.rotate_degrees > 0:
                angle = random.uniform(-self.rotate_degrees, self.rotate_degrees)
                img_t1 = TF.rotate(img_t1, angle, interpolation=TF.InterpolationMode.BILINEAR)
                img_t2 = TF.rotate(img_t2, angle, interpolation=TF.InterpolationMode.BILINEAR)
                mask_pil = TF.rotate(mask_pil, angle, interpolation=TF.InterpolationMode.NEAREST)

        # Convert to Tensors
        t1_tensor = TF.to_tensor(img_t1)  # [3, H, W] in [0, 1]
        t2_tensor = TF.to_tensor(img_t2)  # [3, H, W] in [0, 1]
        
        mask_tensor = TF.to_tensor(mask_pil)  # [1, H, W] in [0, 1]
        mask_tensor = (mask_tensor > 0.5).float()

        # ImageNet Normalization
        t1_tensor = TF.normalize(t1_tensor, mean=self.normalize_mean, std=self.normalize_std)
        t2_tensor = TF.normalize(t2_tensor, mean=self.normalize_mean, std=self.normalize_std)

        return t1_tensor, t2_tensor, mask_tensor

