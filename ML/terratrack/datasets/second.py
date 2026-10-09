"""SECOND Dataset Adapter for binary change detection."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset

from .base import PairedTransform


class SECONDAdapter(Dataset):
    """Adapter for SECOND land-cover change-detection dataset.
    
    T1: im1/
    T2: im2/
    Semantic change masks: label1/ and label2/
    Binary change definition: np.any(label1 != label2, axis=-1)
    """
    def __init__(
        self,
        root_dir: str | Path,
        split: str = "train",
        transform: Optional[PairedTransform] = None,
        val_ratio: float = 0.15,
        random_seed: int = 42,
    ):
        super().__init__()
        self.root_dir = Path(root_dir)
        self.split = split.lower()
        self.transform = transform or PairedTransform(is_train=(self.split == "train"))
        
        # SECOND original packaging provides 'train' (2968) and 'test' (1694).
        # When split='val', split from 'train' using deterministic seeding to avoid geographic leakage.
        source_folder = "train" if self.split in ["train", "val"] else "test"
        self.source_dir = self.root_dir / source_folder
        if not self.source_dir.exists():
            raise FileNotFoundError(f"SECOND directory does not exist: {self.source_dir}")

        self.dir_t1 = self.source_dir / "im1"
        self.dir_t2 = self.source_dir / "im2"
        self.dir_l1 = self.source_dir / "label1"
        self.dir_l2 = self.source_dir / "label2"

        all_ids = sorted([
            f for f in os.listdir(self.dir_t1)
            if f.lower().endswith((".png", ".jpg", ".tif"))
        ])

        if self.split in ["train", "val"]:
            rng = np.random.RandomState(random_seed)
            shuffled = rng.permutation(all_ids)
            n_val = int(len(all_ids) * val_ratio)
            if self.split == "val":
                self.ids = sorted(shuffled[:n_val].tolist())
            else:
                self.ids = sorted(shuffled[n_val:].tolist())
        else:
            self.ids = all_ids

        # Verify alignment
        for sample_id in self.ids:
            if not (self.dir_t2 / sample_id).exists():
                raise FileNotFoundError(f"Missing T2 match for {sample_id} in {self.dir_t2}")
            if not (self.dir_l1 / sample_id).exists():
                raise FileNotFoundError(f"Missing label1 match for {sample_id} in {self.dir_l1}")
            if not (self.dir_l2 / sample_id).exists():
                raise FileNotFoundError(f"Missing label2 match for {sample_id} in {self.dir_l2}")

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        sample_id = self.ids[idx]
        t1_path = self.dir_t1 / sample_id
        t2_path = self.dir_t2 / sample_id
        l1_path = self.dir_l1 / sample_id
        l2_path = self.dir_l2 / sample_id

        img_t1 = Image.open(t1_path).convert("RGB")
        img_t2 = Image.open(t2_path).convert("RGB")
        
        # Load semantic labels to extract binary change
        arr_l1 = np.array(Image.open(l1_path))
        arr_l2 = np.array(Image.open(l2_path))
        
        # A pixel changed if its land cover category differs between T1 and T2
        diff = np.any(arr_l1 != arr_l2, axis=-1)
        mask_bin = diff.astype(np.float32)

        t1_tensor, t2_tensor, mask_tensor = self.transform(img_t1, img_t2, mask_bin)

        return {
            "dataset": "SECOND",
            "id": sample_id,
            "image_t1": t1_tensor,
            "image_t2": t2_tensor,
            "mask": mask_tensor,
            "split": self.split,
            "metadata": {
                "t1_path": str(t1_path),
                "t2_path": str(t2_path),
                "l1_path": str(l1_path),
                "l2_path": str(l2_path),
                "orig_size": img_t1.size
            }
        }

