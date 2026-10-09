"""Smoke test verifying dataset loaders, model forward pass, and loss computation."""

import sys
from pathlib import Path

# Add ML root to sys.path so terratrack can be resolved
ml_root = Path(__file__).resolve().parent.parent
if str(ml_root) not in sys.path:
    sys.path.insert(0, str(ml_root))

import torch
from terratrack.datasets.base import PairedTransform
from terratrack.datasets.levir_cd import LEVIRCDAdapter
from terratrack.models.siamese_unet import SiameseResNetUNet
from terratrack.losses.change_losses import BCEDiceLoss

def test_pipeline():
    ds_path = ml_root / "datasets" / "LEVIR-CD"
    
    # 1. Dataset loading
    print("Testing LEVIR-CD Adapter...")
    ds = LEVIRCDAdapter(ds_path, split="val", transform=PairedTransform(target_size=(256, 256), is_train=False))
    sample = ds[0]
    t1 = sample["image_t1"].unsqueeze(0)
    t2 = sample["image_t2"].unsqueeze(0)
    mask = sample["mask"].unsqueeze(0)
    
    assert t1.shape == (1, 3, 256, 256), f"Unexpected t1 shape: {t1.shape}"
    assert t2.shape == (1, 3, 256, 256), f"Unexpected t2 shape: {t2.shape}"
    assert mask.shape == (1, 1, 256, 256), f"Unexpected mask shape: {mask.shape}"
    print(f"Sample loaded: t1={t1.shape}, t2={t2.shape}, mask={mask.shape}")
    
    # 2. Model initialization & forward pass
    print("Testing SiameseResNetUNet forward pass...")
    model = SiameseResNetUNet(pretrained=False)
    logits = model(t1, t2)
    assert logits.shape == (1, 1, 256, 256), f"Unexpected logits shape: {logits.shape}"
    print(f"Forward pass successful: logits={logits.shape}")
    
    # 3. Loss calculation
    print("Testing BCEDiceLoss calculation...")
    criterion = BCEDiceLoss()
    loss = criterion(logits, mask)
    assert loss.item() >= 0, f"Loss is negative: {loss.item()}"
    print(f"Loss computed successfully: {loss.item():.4f}")
    
    print("\nALL SMOKE TESTS PASSED!")

if __name__ == "__main__":
    test_pipeline()

