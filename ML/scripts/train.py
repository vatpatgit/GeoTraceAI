"""Main entry point for training the TerraTrack Change Detection pipeline."""

import argparse
import os
import sys
from pathlib import Path

# Add ML root directory to sys.path
ml_root = Path(__file__).resolve().parent.parent
if str(ml_root) not in sys.path:
    sys.path.insert(0, str(ml_root))

import random
import numpy as np
import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader
import yaml

from terratrack.datasets.base import PairedTransform
from terratrack.datasets.levir_cd import LEVIRCDAdapter
from terratrack.datasets.s2looking import S2LookingAdapter
from terratrack.datasets.second import SECONDAdapter
from terratrack.datasets.sysu_cd import SYSUCDAdapter
from terratrack.datasets.unified import UnifiedChangeDataset
from terratrack.models.siamese_unet import SiameseResNetUNet
from terratrack.losses.change_losses import BCEDiceLoss, FocalLoss
from terratrack.training.trainer import ChangeTrainer


def set_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def build_dataset(name: str, root_dir: Path, split: str, size: int) -> torch.utils.data.Dataset:
    t = PairedTransform(target_size=(size, size), is_train=(split == "train"))
    name_lower = name.lower()
    if "levir" in name_lower:
        return LEVIRCDAdapter(root_dir, split=split, transform=t)
    elif "s2looking" in name_lower:
        return S2LookingAdapter(root_dir, split=split, transform=t)
    elif "second" in name_lower:
        return SECONDAdapter(root_dir, split=split, transform=t)
    elif "sysu" in name_lower:
        return SYSUCDAdapter(root_dir, split=split, transform=t)
    else:
        raise ValueError(f"Unknown dataset: {name}")


def main():
    parser = argparse.ArgumentParser(description="TerraTrack Change Detection Training")
    parser.add_argument("--config", type=str, default="configs/change_detection.yaml")
    parser.add_argument("--dataset", type=str, default=None, help="Override dataset name (e.g. SECOND, LEVIR-CD)")
    parser.add_argument("--epochs", type=int, default=None, help="Override epoch count")
    parser.add_argument("--batch-size", type=int, default=None, help="Override batch size")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if args.dataset:
        config["data"]["dataset"] = args.dataset
        config["training"]["experiment_name"] = f"{args.dataset.lower()}_baseline"
    if args.epochs:
        config["training"]["epochs"] = args.epochs
    if args.batch_size:
        config["data"]["batch_size"] = args.batch_size

    set_seed(config.get("seed", 42))

    # Detect Device & report hardware
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("\n" + "=" * 60)
    print(f"Device: {device.type.upper()}")
    if device.type == "cuda":
        print(f"GPU Name: {torch.cuda.get_device_name(0)}")
        print(f"Total VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")
    print(f"Dataset Mode: {config['data']['mode'].upper()} ({config['data']['dataset']})")
    print("=" * 60)

    # Resolve paths relative to ML folder
    ml_root = Path(__file__).resolve().parent.parent
    ds_name = config["data"]["dataset"]
    img_size = config["data"]["image_size"]

    if ds_name == "LEVIR-CD":
        raw_path = ml_root / "datasets" / "LEVIR-CD"
    elif ds_name == "S2Looking":
        raw_path = ml_root / "datasets" / "S2Looking" / "S2Looking"
    elif ds_name == "SECOND":
        raw_path = ml_root / "datasets" / "second_dataset"
    else:
        raw_path = ml_root / config["data"]["root_dir"]

    # Datasets & Loaders
    train_ds = build_dataset(ds_name, raw_path, "train", img_size)
    val_ds = build_dataset(ds_name, raw_path, "val", img_size)

    bs = config["data"]["batch_size"]
    nw = config["data"]["num_workers"]
    train_loader = DataLoader(train_ds, batch_size=bs, shuffle=True, num_workers=nw, pin_memory=(device.type == "cuda"))
    val_loader = DataLoader(val_ds, batch_size=bs, shuffle=False, num_workers=nw, pin_memory=(device.type == "cuda"))

    # Architecture
    model = SiameseResNetUNet(
        pretrained=config["model"]["pretrained"],
        encoder_checkpoint=config["model"]["checkpoint"],
        input_channels=config["model"]["input_channels"],
        num_classes=config["model"]["num_classes"],
        fusion_mode=config["model"]["fusion_mode"],
    )

    # Loss
    if config["loss"]["type"] == "bce_dice":
        criterion = BCEDiceLoss(
            bce_weight=config["loss"]["bce_weight"],
            dice_weight=config["loss"]["dice_weight"],
            pos_weight=config["loss"].get("pos_weight", 1.0),
        )
    elif config["loss"]["type"] == "focal":
        criterion = FocalLoss()
    else:
        raise ValueError(f"Unknown loss: {config['loss']['type']}")

    # Optimizer with differential learning rate (lower for pretrained encoder)
    encoder_lr = float(config["optimizer"]["encoder_lr"])
    decoder_lr = float(config["optimizer"]["decoder_lr"])
    optimizer = AdamW([
        {"params": model.encoder.parameters(), "lr": encoder_lr},
        {"params": model.decoder.parameters(), "lr": decoder_lr},
    ], weight_decay=float(config["optimizer"]["weight_decay"]))

    scheduler = CosineAnnealingLR(
        optimizer,
        T_max=config["training"]["epochs"],
        eta_min=float(config["scheduler"]["eta_min"])
    )

    exp_dir = ml_root / "experiments" / config["training"]["experiment_name"]

    trainer = ChangeTrainer(
        model=model,
        criterion=criterion,
        optimizer=optimizer,
        scheduler=scheduler,
        device=device,
        exp_dir=exp_dir,
        use_amp=config["training"]["mixed_precision"],
        gradient_clip=config["training"]["gradient_clip"],
    )

    trainer.fit(
        train_loader=train_loader,
        val_loader=val_loader,
        epochs=config["training"]["epochs"],
        config=config,
    )


if __name__ == "__main__":
    main()
