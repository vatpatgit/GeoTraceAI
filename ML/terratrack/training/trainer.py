"""Modular Trainer for Siamese Change Detection."""

import csv
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import torch
import torch.nn as nn
from torch.optim import Optimizer
from torch.optim.lr_scheduler import _LRScheduler
from torch.utils.data import DataLoader
from tqdm import tqdm

from terratrack.evaluation.metrics import compute_metrics, find_best_threshold
from terratrack.evaluation.visualization import save_prediction_grid


class ChangeTrainer:
    """Production research trainer for Siamese ResNet50 + U-Net Change Detection."""

    def __init__(
        self,
        model: nn.Module,
        criterion: nn.Module,
        optimizer: Optimizer,
        scheduler: Optional[_LRScheduler],
        device: torch.device,
        exp_dir: str | Path,
        use_amp: bool = True,
        gradient_clip: float = 1.0,
    ):
        self.model = model.to(device)
        self.criterion = criterion
        self.optimizer = optimizer
        self.scheduler = scheduler
        self.device = device
        self.exp_dir = Path(exp_dir)
        self.use_amp = use_amp and device.type == "cuda"
        self.gradient_clip = gradient_clip

        self.scaler = torch.amp.GradScaler("cuda", enabled=self.use_amp)
        self.best_iou = -1.0
        self.best_threshold = 0.50

        self.exp_dir.mkdir(parents=True, exist_ok=True)
        (self.exp_dir / "plots").mkdir(exist_ok=True)
        (self.exp_dir / "predictions").mkdir(exist_ok=True)

        self.csv_path = self.exp_dir / "training_log.csv"
        if not self.csv_path.exists():
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "epoch", "train_loss", "val_loss",
                    "precision", "recall", "f1", "change_iou",
                    "best_threshold", "lr"
                ])

    def train_epoch(self, loader: DataLoader, epoch: int) -> float:
        self.model.train()
        total_loss = 0.0
        pbar = tqdm(loader, desc=f"Train Epoch {epoch:03d}")

        for batch in pbar:
            t1 = batch["image_t1"].to(self.device, non_blocking=True)
            t2 = batch["image_t2"].to(self.device, non_blocking=True)
            targets = batch["mask"].to(self.device, non_blocking=True)

            self.optimizer.zero_grad()

            with torch.amp.autocast("cuda", enabled=self.use_amp):
                logits = self.model(t1, t2)
                loss = self.criterion(logits, targets)

            self.scaler.scale(loss).backward()
            if self.gradient_clip > 0:
                self.scaler.unscale_(self.optimizer)
                nn.utils.clip_grad_norm_(self.model.parameters(), self.gradient_clip)

            self.scaler.step(self.optimizer)
            self.scaler.update()

            total_loss += loss.item()
            pbar.set_postfix({"loss": f"{loss.item():.4f}"})

        return total_loss / max(len(loader), 1)

    @torch.no_grad()
    def validate(
        self, loader: DataLoader, epoch: int, save_visuals: bool = True
    ) -> Tuple[float, Dict[str, float], float]:
        self.model.eval()
        total_loss = 0.0
        all_probs = []
        all_targets = []
        saved_visuals = False

        for batch in loader:
            t1 = batch["image_t1"].to(self.device, non_blocking=True)
            t2 = batch["image_t2"].to(self.device, non_blocking=True)
            targets = batch["mask"].to(self.device, non_blocking=True)

            with torch.amp.autocast("cuda", enabled=self.use_amp):
                logits = self.model(t1, t2)
                loss = self.criterion(logits, targets)

            total_loss += loss.item()
            probs = torch.sigmoid(logits)

            all_probs.append(probs.cpu().numpy())
            all_targets.append(targets.cpu().numpy())

            if save_visuals and not saved_visuals:
                pred_binary = (probs >= self.best_threshold).float()
                save_prediction_grid(
                    t1, t2, targets, pred_binary,
                    self.exp_dir / "predictions" / f"epoch_{epoch:03d}.png"
                )
                saved_visuals = True

        avg_loss = total_loss / max(len(loader), 1)
        best_thresh, metrics = find_best_threshold(all_probs, all_targets)
        return avg_loss, metrics, best_thresh

    def save_checkpoint(
        self,
        epoch: int,
        metrics: Dict[str, float],
        is_best: bool,
        config: Optional[Dict[str, Any]] = None,
    ):
        state = {
            "epoch": epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict() if self.scheduler else None,
            "metrics": metrics,
            "best_threshold": self.best_threshold,
            "config": config,
        }
        latest_path = self.exp_dir / "latest_model.pth"
        torch.save(state, latest_path)

        if is_best:
            best_path = self.exp_dir / "best_model.pth"
            torch.save(state, best_path)
            with open(self.exp_dir / "metrics.json", "w", encoding="utf-8") as f:
                json.dump({"best_epoch": epoch, "metrics": metrics, "best_threshold": self.best_threshold}, f, indent=2)

    def fit(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        epochs: int,
        config: Optional[Dict[str, Any]] = None,
    ):
        print(f"\nStarting training on {self.device.type.upper()} ({epochs} epochs)...")
        for epoch in range(1, epochs + 1):
            train_loss = self.train_epoch(train_loader, epoch)
            val_loss, metrics, best_thresh = self.validate(val_loader, epoch)

            self.best_threshold = best_thresh
            is_best = metrics["change_iou"] > self.best_iou
            if is_best:
                self.best_iou = metrics["change_iou"]

            cur_lr = self.optimizer.param_groups[0]["lr"]
            if self.scheduler:
                self.scheduler.step()

            # Record in CSV
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    epoch, f"{train_loss:.5f}", f"{val_loss:.5f}",
                    f"{metrics['precision']:.4f}", f"{metrics['recall']:.4f}",
                    f"{metrics['f1']:.4f}", f"{metrics['change_iou']:.4f}",
                    f"{best_thresh:.2f}", f"{cur_lr:.6f}"
                ])

            self.save_checkpoint(epoch, metrics, is_best, config)

            print(
                f"Epoch {epoch:03d} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | "
                f"Val F1: {metrics['f1']:.4f} | Change IoU: {metrics['change_iou']:.4f} "
                f"{'(BEST)' if is_best else ''}"
            )

