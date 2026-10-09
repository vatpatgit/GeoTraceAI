"""Visual verification of sample triplets across datasets."""

import os
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt

def verify_and_plot():
    datasets_root = Path(__file__).resolve().parent.parent / "datasets"
    out_dir = Path(__file__).resolve().parent.parent / "artifacts" / "inspection_samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. LEVIR-CD sample
    levir_dir = datasets_root / "LEVIR-CD" / "train"
    f_levir = "train_1.png"
    levir_t1 = Image.open(levir_dir / "A" / f_levir).convert("RGB")
    levir_t2 = Image.open(levir_dir / "B" / f_levir).convert("RGB")
    levir_mask = np.array(Image.open(levir_dir / "label" / f_levir))
    levir_bin = (levir_mask > 127).astype(np.float32)
    
    # 2. S2Looking sample
    s2_dir = datasets_root / "S2Looking" / "S2Looking" / "train"
    f_s2 = "1.png"
    s2_t1 = Image.open(s2_dir / "Image1" / f_s2).convert("RGB")
    s2_t2 = Image.open(s2_dir / "Image2" / f_s2).convert("RGB")
    s2_mask = np.array(Image.open(s2_dir / "label" / f_s2))
    s2_bin = (s2_mask > 127).astype(np.float32)
    
    # 3. SECOND sample
    second_dir = datasets_root / "second_dataset" / "train"
    f_sec = "00003.png"
    sec_t1 = Image.open(second_dir / "im1" / f_sec).convert("RGB")
    sec_t2 = Image.open(second_dir / "im2" / f_sec).convert("RGB")
    l1 = np.array(Image.open(second_dir / "label1" / f_sec))
    l2 = np.array(Image.open(second_dir / "label2" / f_sec))
    sec_bin = np.any(l1 != l2, axis=-1).astype(np.float32)
    
    samples = [
        ("LEVIR-CD (train_1.png)", levir_t1, levir_t2, levir_bin),
        ("S2Looking (1.png)", s2_t1, s2_t2, s2_bin),
        ("SECOND (00003.png)", sec_t1, sec_t2, sec_bin),
    ]
    
    fig, axes = plt.subplots(len(samples), 3, figsize=(12, 4 * len(samples)))
    for idx, (name, t1, t2, mask) in enumerate(samples):
        axes[idx, 0].imshow(t1)
        axes[idx, 0].set_title(f"{name} - T1")
        axes[idx, 0].axis("off")
        
        axes[idx, 1].imshow(t2)
        axes[idx, 1].set_title(f"{name} - T2")
        axes[idx, 1].axis("off")
        
        axes[idx, 2].imshow(mask, cmap="gray")
        axes[idx, 2].set_title(f"Binary Change Mask ({mask.mean()*100:.1f}%)")
        axes[idx, 2].axis("off")
        
    plt.tight_layout()
    save_path = out_dir / "sample_triplets_check.png"
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"Sample triplet visualization saved successfully to: {save_path}")

if __name__ == "__main__":
    verify_and_plot()

