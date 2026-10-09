"""LEVIR-CD Dataset Adapter."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset

from .base import PairedTransform


class LEVIRCDAdapter(Dataset):
    """Adapter for LEVIR-CD building change-detection dataset.
    
    T1: A/
    T2: B/
    Mask: label/ (0 = unchanged, 255 = change)
    """
    def __init__(
        self,
        root_dir: str | Path,
        split: str = "train",
        transform: Optional[PairedTransform] = None,
    ):
        super().__init__()
        self.root_dir = Path(root_dir)
        self.split = split.lower()
        self.transform = transform or PairedTransform(is_train=(self.split == "train"))
        
        self.split_dir = self.root_dir / self.split
        if not self.split_dir.exists():
            raise FileNotFoundError(f"LEVIR-CD split directory does not exist: {self.split_dir}")

        self.dir_t1 = self.split_dir / "A"
        self.dir_t2 = self.split_dir / "B"
        self.dir_label = self.split_dir / "label"

        self.ids = sorted([
            f for f in os.listdir(self.dir_t1)
            if f.lower().endswith((".png", ".jpg", ".tif"))
        ])
        
        # Verify alignment
        for sample_id in self.ids:
            if not (self.dir_t2 / sample_id).exists():
                raise FileNotFoundError(f"Missing T2 match for {sample_id} in {self.dir_t2}")
            if not (self.dir_label / sample_id).exists():
                raise FileNotFoundError(f"Missing label match for {sample_id} in {self.dir_label}")

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        sample_id = self.ids[idx]
        t1_path = self.dir_t1 / sample_id
        t2_path = self.dir_t2 / sample_id
        mask_path = self.dir_label / sample_id

        img_t1 = Image.open(t1_path).convert("RGB")
        img_t2 = Image.open(t2_path).convert("RGB")
        
        # Mask conversion: values are 0 or 255 -> binary {0.0, 1.0}
        mask_raw = np.array(Image.open(mask_path).convert("L"))
        mask_bin = (mask_raw > 127).astype(np.float32)

        t1_tensor, t2_tensor, mask_tensor = self.transform(img_t1, img_t2, mask_bin)

        return {
            "dataset": "LEVIR-CD",
            "id": sample_id,
            "image_t1": t1_tensor,
            "image_t2": t2_tensor,
            "mask": mask_tensor,
            "split": self.split,
            "metadata": {
                "t1_path": str(t1_path),
                "t2_path": str(t2_path),
                "mask_path": str(mask_path),
                "orig_size": img_t1.size
            }
        }

