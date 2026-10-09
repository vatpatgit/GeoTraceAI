"""Prediction and error visualization routines."""

from pathlib import Path
from typing import List, Optional
import matplotlib.pyplot as plt
import numpy as np
import torch


def save_prediction_grid(
    t1_tensors: torch.Tensor,
    t2_tensors: torch.Tensor,
    gt_masks: torch.Tensor,
    pred_masks: torch.Tensor,
    save_path: str | Path,
    max_samples: int = 4,
    mean: List[float] = [0.485, 0.456, 0.406],
    std: List[float] = [0.229, 0.224, 0.225],
):
    """Saves a multi-row visual comparison: [T1] [T2] [Ground Truth] [Prediction] [Error Map].
    
    Error Map:
        Green = True Positive
        Red = False Positive
        Blue = False Negative
        Black = True Negative
    """
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    n_samples = min(len(t1_tensors), max_samples)
    fig, axes = plt.subplots(n_samples, 5, figsize=(15, 3.2 * n_samples))
    if n_samples == 1:
        axes = np.expand_dims(axes, 0)

    mean_arr = np.array(mean).reshape(3, 1, 1)
    std_arr = np.array(std).reshape(3, 1, 1)

    for i in range(n_samples):
        # Denormalize images for plotting
        img1 = (t1_tensors[i].cpu().numpy() * std_arr + mean_arr).clip(0, 1).transpose(1, 2, 0)
        img2 = (t2_tensors[i].cpu().numpy() * std_arr + mean_arr).clip(0, 1).transpose(1, 2, 0)
        gt = gt_masks[i, 0].cpu().numpy()
        pred = pred_masks[i, 0].cpu().numpy()

        # Build error map
        err = np.zeros((*gt.shape, 3), dtype=np.float32)
        err[(gt == 1) & (pred == 1)] = [0, 1, 0]  # Green: TP
        err[(gt == 0) & (pred == 1)] = [1, 0, 0]  # Red: FP
        err[(gt == 1) & (pred == 0)] = [0, 0.4, 1]  # Blue: FN

        axes[i, 0].imshow(img1)
        axes[i, 0].set_title("T1 (Before)")
        axes[i, 0].axis("off")

        axes[i, 1].imshow(img2)
        axes[i, 1].set_title("T2 (After)")
        axes[i, 1].axis("off")

        axes[i, 2].imshow(gt, cmap="gray")
        axes[i, 2].set_title(f"Ground Truth ({gt.mean()*100:.1f}%)")
        axes[i, 2].axis("off")

        axes[i, 3].imshow(pred, cmap="gray")
        axes[i, 3].set_title(f"Prediction ({pred.mean()*100:.1f}%)")
        axes[i, 3].axis("off")

        axes[i, 4].imshow(err)
        axes[i, 4].set_title("Errors (G:TP, R:FP, B:FN)")
        axes[i, 4].axis("off")

    plt.tight_layout()
    plt.savefig(save_path, dpi=120)
    plt.close()

