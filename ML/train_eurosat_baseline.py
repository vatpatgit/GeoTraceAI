"""Phase 1: EuroSAT Multispectral (13-band) & RGB Baseline Training."""

import argparse
import csv
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image
from sklearn.metrics import classification_report, f1_score
import tifffile
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

# ---------------------------------------------------------
# Transforms
# ---------------------------------------------------------

TRAIN_TRANSFORMS = transforms.Compose(
    [
        transforms.Resize((256, 256)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomVerticalFlip(p=0.5),
        transforms.RandomRotation(degrees=15),
        transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
        ),
    ]
)

EVAL_TRANSFORMS = transforms.Compose(
    [
        transforms.Resize((256, 256)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
        ),
    ]
)

# ---------------------------------------------------------
# Multispectral Image Loader
# ---------------------------------------------------------


def load_sentinel_image(img_path: Path) -> Image.Image:
    """Read 13-band Sentinel-2 TIFFs or standard RGB files directly without triggering libtiff warnings."""
    path_str = str(img_path)

    # Directly route .tif / .tiff files to tifffile to bypass PIL's libtiff warning
    if path_str.lower().endswith((".tif", ".tiff")):
        arr = tifffile.imread(path_str)

        # Extract RGB bands: B04 (Red - idx 3), B03 (Green - idx 2), B02 (Blue - idx 1)
        if arr.ndim == 3:
            if arr.shape[0] == 13:
                r, g, b = arr[3, :, :], arr[2, :, :], arr[1, :, :]
            elif arr.shape[2] == 13:
                r, g, b = arr[:, :, 3], arr[:, :, 2], arr[:, :, 1]
            elif arr.shape[0] == 3:
                r, g, b = arr[0, :, :], arr[1, :, :], arr[2, :, :]
            else:
                r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        else:
            r = g = b = arr

        rgb = np.stack([r, g, b], axis=-1).astype(np.float32)

        # Normalize Sentinel-2 surface reflectance (0-3500 -> 0-255 uint8)
        rgb = np.clip(rgb / 3500.0 * 255.0, 0, 255).astype(np.uint8)
        return Image.fromarray(rgb)

    return Image.open(img_path).convert("RGB")


# ---------------------------------------------------------
# Custom CSV Dataset Loader
# ---------------------------------------------------------


class EuroSATCSVDataset(Dataset):
    def __init__(
        self,
        csv_file: Path,
        root_dir: Path,
        label_to_idx: Dict[str, int],
        transform=None,
    ):
        self.root_dir = Path(root_dir)
        self.transform = transform
        self.samples: List[Tuple[Path, int]] = []

        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                filename_key = next(
                    (
                        k
                        for k in [
                            "Filename",
                            "filename",
                            "filepath",
                            "image_path",
                            "Path",
                        ]
                        if k in row
                    ),
                    list(row.keys())[0],
                )
                label_key = next(
                    (
                        k
                        for k in [
                            "Label",
                            "label",
                            "ClassName",
                            "class_name",
                            "Class",
                        ]
                        if k in row
                    ),
                    list(row.keys())[1],
                )

                raw_filename = row[filename_key].strip()
                raw_label = row[label_key].strip()

                if raw_label in label_to_idx:
                    label_idx = label_to_idx[raw_label]
                elif raw_label.isdigit() and int(raw_label) in label_to_idx.values():
                    label_idx = int(raw_label)
                else:
                    label_idx = int(label_to_idx.get(raw_label, 0))

                img_path = self.root_dir / raw_filename
                if not img_path.exists():
                    img_path = self.root_dir / raw_label / Path(raw_filename).name

                if img_path.exists():
                    self.samples.append((img_path, label_idx))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        img_path, label = self.samples[idx]
        image = load_sentinel_image(img_path)
        if self.transform:
            image = self.transform(image)
        return image, label


def get_dataloaders(
    data_dir: str, batch_size: int = 32
) -> Tuple[Dict[str, DataLoader], Dict[int, str]]:
    root = Path(data_dir)

    label_map_file = root / "label_map.json"
    if label_map_file.exists():
        with open(label_map_file, "r", encoding="utf-8") as f:
            raw_map = json.load(f)
            if all(k.isdigit() for k in raw_map.keys()):
                idx_to_class = {int(k): v for k, v in raw_map.items()}
                class_to_idx = {v: int(k) for k, v in raw_map.items()}
            else:
                class_to_idx = {k: int(v) for k, v in raw_map.items()}
                idx_to_class = {int(v): k for k, v in raw_map.items()}
    else:
        classes = sorted([d.name for d in root.iterdir() if d.is_dir()])
        class_to_idx = {cls: idx for idx, cls in enumerate(classes)}
        idx_to_class = {idx: cls for cls, idx in class_to_idx.items()}

    train_ds = EuroSATCSVDataset(
        root / "train.csv", root, class_to_idx, transform=TRAIN_TRANSFORMS
    )
    val_csv = root / "validation.csv" if (root / "validation.csv").exists() else root / "val.csv"
    val_ds = EuroSATCSVDataset(
        val_csv, root, class_to_idx, transform=EVAL_TRANSFORMS
    )
    test_ds = EuroSATCSVDataset(
        root / "test.csv", root, class_to_idx, transform=EVAL_TRANSFORMS
    )

    print(
        f"Dataset loaded: {len(train_ds)} train | {len(val_ds)} val | {len(test_ds)} test samples across {len(class_to_idx)} classes."
    )

    dataloaders = {
        "train": DataLoader(
            train_ds,
            batch_size=batch_size,
            shuffle=True,
            num_workers=0,
            pin_memory=torch.cuda.is_available(),
        ),
        "val": DataLoader(
            val_ds,
            batch_size=batch_size,
            shuffle=False,
            num_workers=0,
            pin_memory=torch.cuda.is_available(),
        ),
        "test": DataLoader(
            test_ds,
            batch_size=batch_size,
            shuffle=False,
            num_workers=0,
            pin_memory=torch.cuda.is_available(),
        ),
    }

    return dataloaders, idx_to_class


# ---------------------------------------------------------
# Model & Training Loop
# ---------------------------------------------------------


def build_eurosat_resnet50(num_classes: int = 10) -> nn.Module:
    model = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
    in_features = model.fc.in_features
    model.fc = nn.Sequential(
        nn.Dropout(p=0.3),
        nn.Linear(in_features, num_classes),
    )
    return model


def run_training(
    data_dir: str,
    output_dir: str = "ML/artifacts",
    epochs: int = 25,
    batch_size: int = 32,
    lr: float = 3e-4,
):
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    dataloaders, idx_to_class = get_dataloaders(data_dir, batch_size=batch_size)
    model = build_eurosat_resnet50(num_classes=len(idx_to_class)).to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = AdamW(model.parameters(), lr=lr, weight_decay=1e-2)
    scheduler = CosineAnnealingLR(optimizer, T_max=epochs)
    scaler = torch.amp.GradScaler("cuda", enabled=torch.cuda.is_available())

    best_val_f1 = 0.0
    best_model_path = out_path / "terratrack_landcover_resnet50.pth"
    encoder_path = out_path / "resnet50_feature_extractor.pth"

    print(f"Starting training on {device} (Device Name: {torch.cuda.get_device_name(0)})...")

    for epoch in range(1, epochs + 1):
        t0 = time.time()

        # Training Phase
        model.train()
        train_loss, train_correct, train_total = 0.0, 0, 0
        for inputs, labels in dataloaders["train"]:
            inputs, labels = inputs.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)

            with torch.amp.autocast("cuda", enabled=torch.cuda.is_available()):
                outputs = model(inputs)
                loss = criterion(outputs, labels)

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            train_loss += loss.item() * inputs.size(0)
            preds = outputs.argmax(dim=1)
            train_correct += (preds == labels).sum().item()
            train_total += labels.size(0)

        scheduler.step()
        epoch_train_loss = train_loss / train_total
        epoch_train_acc = train_correct / train_total

        # Validation Phase
        model.eval()
        val_loss, val_total = 0.0, 0
        all_preds, all_labels = [], []
        with torch.no_grad():
            for inputs, labels in dataloaders["val"]:
                inputs, labels = inputs.to(device), labels.to(device)
                with torch.amp.autocast("cuda", enabled=torch.cuda.is_available()):
                    outputs = model(inputs)
                    loss = criterion(outputs, labels)

                val_loss += loss.item() * inputs.size(0)
                preds = outputs.argmax(dim=1)
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())
                val_total += labels.size(0)

        epoch_val_loss = val_loss / val_total
        epoch_val_acc = np.mean(np.array(all_preds) == np.array(all_labels))
        epoch_val_f1 = f1_score(all_labels, all_preds, average="macro")
        elapsed = time.time() - t0

        print(
            f"Epoch [{epoch:02d}/{epochs:02d}] ({elapsed:.1f}s) | "
            f"Train Loss: {epoch_train_loss:.4f} Acc: {epoch_train_acc:.4f} | "
            f"Val Loss: {epoch_val_loss:.4f} Acc: {epoch_val_acc:.4f} F1: {epoch_val_f1:.4f}"
        )

        if epoch_val_f1 > best_val_f1:
            best_val_f1 = epoch_val_f1
            torch.save(model.state_dict(), best_model_path)
            encoder_state = {
                k: v for k, v in model.state_dict().items() if not k.startswith("fc.")
            }
            torch.save(encoder_state, encoder_path)
            print(f"  -> Saved best encoder checkpoint (Val F1: {epoch_val_f1:.4f})")

    # Evaluation on Test Set
    print("\n--- Final Test Evaluation ---")
    model.load_state_dict(torch.load(best_model_path, map_location=device))
    model.eval()
    test_preds, test_labels = [], []
    with torch.no_grad():
        for inputs, labels in dataloaders["test"]:
            inputs = inputs.to(device)
            outputs = model(inputs)
            test_preds.extend(outputs.argmax(dim=1).cpu().numpy())
            test_labels.extend(labels.numpy())

    print(
        classification_report(
            test_labels,
            test_preds,
            target_names=[idx_to_class[i] for i in range(len(idx_to_class))],
        )
    )
    print(f"Pretrained weights exported to: {encoder_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data_dir",
        type=str,
        required=True,
        help="Path to folder containing CSV files and class folders",
    )
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--output_dir", type=str, default="ML/artifacts")
    args = parser.parse_args()

    run_training(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
    )