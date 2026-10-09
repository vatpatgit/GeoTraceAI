"""SYSU-CD Dataset Adapter."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset

from .base import PairedTransform


class SYSUCDAdapter(Dataset):
    """Adapter for SYSU-CD dataset.
    
    Standard folder structure:
    train/val/test splits, with:
    time1/ or T1/
    time2/ or T2/
    label/ (0 = unchanged, 255 = change)
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
            raise FileNotFoundError(f"SYSU-CD split directory does not exist: {self.split_dir}")

        # Resolve directory name variations (time1 vs T1 vs A)
        self.dir_t1 = self._resolve_dir(["time1", "T1", "A"])
        self.dir_t2 = self._resolve_dir(["time2", "T2", "B"])
        self.dir_label = self._resolve_dir(["label", "label1", "gt"])

        self.ids = sorted([
            f for f in os.listdir(self.dir_t1)
            if f.lower().endswith((".png", ".jpg", ".tif"))
        ])

    def _resolve_dir(self, candidates: List[str]) -> Path:
        for c in candidates:
            p = self.split_dir / c
            if p.exists():
                return p
        raise FileNotFoundError(f"None of {candidates} exist in {self.split_dir}")

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        sample_id = self.ids[idx]
        t1_path = self.dir_t1 / sample_id
        t2_path = self.dir_t2 / sample_id
        mask_path = self.dir_label / sample_id

        img_t1 = Image.open(t1_path).convert("RGB")
        img_t2 = Image.open(t2_path).convert("RGB")
        
        mask_raw = np.array(Image.open(mask_path).convert("L"))
        mask_bin = (mask_raw > 127).astype(np.float32)

        t1_tensor, t2_tensor, mask_tensor = self.transform(img_t1, img_t2, mask_bin)

        return {
            "dataset": "SYSU-CD",
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

