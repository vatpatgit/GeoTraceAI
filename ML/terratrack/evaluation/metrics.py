"""Evaluation metrics for Binary Change Detection."""

from typing import Dict, List, Tuple
import numpy as np
import torch


def compute_metrics(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    eps: float = 1e-7,
) -> Dict[str, float]:
    """Compute Precision, Recall, F1 / Dice, Change IoU, Unchanged IoU, and Mean IoU.
    
    Args:
        y_pred: Binary predicted change mask (0 or 1), shape (N,) or (H, W).
        y_true: Binary ground truth mask (0 or 1), shape (N,) or (H, W).
    """
    y_pred = (y_pred > 0.5).astype(np.uint8)
    y_true = (y_true > 0.5).astype(np.uint8)

    tp = np.count_nonzero((y_pred == 1) & (y_true == 1))
    fp = np.count_nonzero((y_pred == 1) & (y_true == 0))
    fn = np.count_nonzero((y_pred == 0) & (y_true == 1))
    tn = np.count_nonzero((y_pred == 0) & (y_true == 0))

    precision = tp / (tp + fp + eps)
    recall = tp / (tp + fn + eps)
    f1 = (2.0 * precision * recall) / (precision + recall + eps)
    change_iou = tp / (tp + fp + fn + eps)
    unchanged_iou = tn / (tn + fp + fn + eps)
    m_iou = (change_iou + unchanged_iou) / 2.0

    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "change_iou": float(change_iou),
        "unchanged_iou": float(unchanged_iou),
        "mean_iou": float(m_iou),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
    }


def find_best_threshold(
    val_probs: List[np.ndarray],
    val_targets: List[np.ndarray],
    candidate_thresholds: Tuple[float, ...] = (0.30, 0.40, 0.50, 0.60, 0.70),
) -> Tuple[float, Dict[str, float]]:
    """Evaluates multiple thresholds on the validation set to find the optimal F1 / IoU score.
    
    Prevents tuning thresholds on the final test set.
    """
    best_thresh = 0.50
    best_iou = -1.0
    best_metrics = {}

    all_probs = np.concatenate([p.ravel() for p in val_probs])
    all_targets = np.concatenate([t.ravel() for t in val_targets])

    for thresh in candidate_thresholds:
        preds = (all_probs >= thresh).astype(np.uint8)
        m = compute_metrics(preds, all_targets)
        if m["change_iou"] > best_iou:
            best_iou = m["change_iou"]
            best_thresh = thresh
            best_metrics = m

    return best_thresh, best_metrics

