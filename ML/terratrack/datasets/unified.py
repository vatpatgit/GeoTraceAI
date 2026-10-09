"""Unified Multi-Dataset Adapter with Weighted Sampling and Cross-Dataset Modes."""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import torch
from torch.utils.data import Dataset, ConcatDataset, WeightedRandomSampler

from .base import PairedTransform
from .levir_cd import LEVIRCDAdapter
from .s2looking import S2LookingAdapter
from .second import SECONDAdapter
from .sysu_cd import SYSUCDAdapter


class UnifiedChangeDataset(Dataset):
    """Unified container for multiple change detection datasets.
    
    Preserves dataset metadata, supports weighted sampling across heterogeneous dataset sizes,
    and supports single-dataset, mixed, and leave-one-out cross-dataset experiments.
    """
    def __init__(
        self,
        datasets: List[Dataset],
        weights: Optional[Dict[str, float]] = None,
    ):
        super().__init__()
        self.datasets = datasets
        self.cumulative_sizes = self._cumsum([len(d) for d in datasets])
        self.total_size = self.cumulative_sizes[-1] if self.cumulative_sizes else 0
        self.weights_config = weights or {}

    @staticmethod
    def _cumsum(sequence: List[int]) -> List[int]:
        out = []
        s = 0
        for x in sequence:
            s += x
            out.append(s)
        return out

    def __len__(self) -> int:
        return self.total_size

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        if idx < 0 or idx >= self.total_size:
            raise IndexError(f"Index {idx} out of range [0, {self.total_size})")
        
        # Locate which dataset contains this index
        dataset_idx = 0
        while dataset_idx < len(self.cumulative_sizes) and idx >= self.cumulative_sizes[dataset_idx]:
            dataset_idx += 1
            
        sample_idx = idx if dataset_idx == 0 else idx - self.cumulative_sizes[dataset_idx - 1]
        return self.datasets[dataset_idx][sample_idx]

    def get_sampler(self) -> WeightedRandomSampler:
        """Constructs a WeightedRandomSampler so larger datasets do not overpower smaller ones."""
        sample_weights = []
        for ds in self.datasets:
            ds_name = ds[0]["dataset"] if len(ds) > 0 else "unknown"
            weight = self.weights_config.get(ds_name, 1.0) / max(len(ds), 1)
            sample_weights.extend([weight] * len(ds))

        tensor_weights = torch.as_tensor(sample_weights, dtype=torch.double)
        return WeightedRandomSampler(weights=tensor_weights, num_samples=len(sample_weights), replacement=True)

