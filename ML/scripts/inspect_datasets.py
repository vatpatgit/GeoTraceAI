"""Dataset inspection and statistical analysis script for TerraTrack Change Detection."""

import argparse
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
from PIL import Image


def inspect_levir_cd(base_dir: Path) -> Dict[str, Any]:
    info = {
        "name": "LEVIR-CD",
        "location": str(base_dir),
        "splits": {},
        "image_size": None,
        "image_channels": None,
        "mask_unique_values": None,
        "changed_pixel_ratio": None,
        "sample_paths": {}
    }
    
    total_changed = 0
    total_pixels = 0
    
    for split in ["train", "val", "test"]:
        split_dir = base_dir / split
        if not split_dir.exists():
            continue
        im_dir = split_dir / "A"
        mask_dir = split_dir / "label"
        files = sorted([f for f in os.listdir(im_dir) if f.lower().endswith(".png")])
        info["splits"][split] = len(files)
        
        if files and split not in info["sample_paths"]:
            f0 = files[0]
            info["sample_paths"][split] = {
                "t1": str(split_dir / "A" / f0),
                "t2": str(split_dir / "B" / f0),
                "mask": str(split_dir / "label" / f0)
            }
            
        # Sample subset for pixel stats
        sample_subset = files[:50]
        for f in sample_subset:
            m_path = mask_dir / f
            m = np.array(Image.open(m_path))
            changed = np.count_nonzero(m > 127)
            total_changed += changed
            total_pixels += m.size
            if info["image_size"] is None:
                im = Image.open(im_dir / f)
                info["image_size"] = im.size
                info["image_channels"] = len(im.getbands())
                info["mask_unique_values"] = np.unique(m).tolist()

    if total_pixels > 0:
        info["changed_pixel_ratio"] = float(total_changed / total_pixels)
    return info


def inspect_s2looking(base_dir: Path) -> Dict[str, Any]:
    info = {
        "name": "S2Looking",
        "location": str(base_dir),
        "splits": {},
        "image_size": None,
        "image_channels": None,
        "mask_unique_values": None,
        "changed_pixel_ratio": None,
        "sample_paths": {}
    }
    
    total_changed = 0
    total_pixels = 0
    
    for split in ["train", "val", "test"]:
        split_dir = base_dir / split
        if not split_dir.exists():
            continue
        im1_dir = split_dir / "Image1"
        im2_dir = split_dir / "Image2"
        mask_dir = split_dir / "label"
        files = sorted([f for f in os.listdir(im1_dir) if f.lower().endswith(".png")])
        info["splits"][split] = len(files)
        
        if files and split not in info["sample_paths"]:
            f0 = files[0]
            info["sample_paths"][split] = {
                "t1": str(im1_dir / f0),
                "t2": str(im2_dir / f0),
                "mask": str(mask_dir / f0)
            }
            
        sample_subset = files[:50]
        for f in sample_subset:
            m_path = mask_dir / f
            m = np.array(Image.open(m_path))
            changed = np.count_nonzero(m > 127)
            total_changed += changed
            total_pixels += m.size
            if info["image_size"] is None:
                im = Image.open(im1_dir / f)
                info["image_size"] = im.size
                info["image_channels"] = len(im.getbands())
                info["mask_unique_values"] = np.unique(m).tolist()

    if total_pixels > 0:
        info["changed_pixel_ratio"] = float(total_changed / total_pixels)
    return info


def inspect_second(base_dir: Path) -> Dict[str, Any]:
    info = {
        "name": "SECOND",
        "location": str(base_dir),
        "splits": {},
        "image_size": None,
        "image_channels": None,
        "mask_unique_values": None,
        "changed_pixel_ratio": None,
        "sample_paths": {}
    }
    
    total_changed = 0
    total_pixels = 0
    
    for split in ["train", "test"]:
        split_dir = base_dir / split
        if not split_dir.exists():
            continue
        im1_dir = split_dir / "im1"
        im2_dir = split_dir / "im2"
        l1_dir = split_dir / "label1"
        l2_dir = split_dir / "label2"
        files = sorted([f for f in os.listdir(im1_dir) if f.lower().endswith(".png")])
        info["splits"][split] = len(files)
        
        if files and split not in info["sample_paths"]:
            f0 = files[0]
            info["sample_paths"][split] = {
                "t1": str(im1_dir / f0),
                "t2": str(im2_dir / f0),
                "label1": str(l1_dir / f0),
                "label2": str(l2_dir / f0)
            }
            
        sample_subset = files[:50]
        for f in sample_subset:
            m1 = np.array(Image.open(l1_dir / f))
            m2 = np.array(Image.open(l2_dir / f))
            diff = np.any(m1 != m2, axis=-1)
            changed = np.count_nonzero(diff)
            total_changed += changed
            total_pixels += diff.size
            if info["image_size"] is None:
                im = Image.open(im1_dir / f)
                info["image_size"] = im.size
                info["image_channels"] = len(im.getbands())
                info["mask_unique_values"] = [0, 1]

    if total_pixels > 0:
        info["changed_pixel_ratio"] = float(total_changed / total_pixels)
    return info


def inspect_sysu_cd(base_dir: Path) -> Dict[str, Any]:
    info = {
        "name": "SYSU-CD",
        "location": str(base_dir),
        "splits": {},
        "image_size": None,
        "image_channels": None,
        "mask_unique_values": None,
        "changed_pixel_ratio": None,
        "sample_paths": {},
        "available": base_dir.exists()
    }
    if not base_dir.exists():
        return info
    
    # If standard SYSU layout (time1, time2, label)
    # Check directory contents
    return info


def main():
    root = Path(__file__).resolve().parent.parent / "datasets"
    print("=" * 70)
    print("TERRATRACK DATASET INSPECTION REPORT")
    print("=" * 70)
    
    datasets = [
        ("LEVIR-CD", root / "LEVIR-CD", inspect_levir_cd),
        ("S2Looking", root / "S2Looking" / "S2Looking", inspect_s2looking),
        ("SECOND", root / "second_dataset", inspect_second),
        ("SYSU-CD", root / "SYSU-CD", inspect_sysu_cd)
    ]
    
    for name, path, func in datasets:
        print(f"\nEvaluating: {name} (Path: {path})")
        if not path.exists():
            print(f"  [STATUS]: Directory NOT FOUND at {path}")
            continue
            
        res = func(path)
        total_samples = sum(res["splits"].values())
        print(f"  Total Samples:        {total_samples}")
        for s, count in res["splits"].items():
            print(f"    - {s.capitalize()} Samples:    {count}")
        print(f"  Image Shape (W, H):   {res['image_size']}")
        print(f"  Number of Channels:   {res['image_channels']}")
        print(f"  Mask Unique Values:   {res['mask_unique_values']}")
        ratio = res['changed_pixel_ratio']
        pct_str = f"{ratio * 100:.2f}%" if ratio is not None else "N/A"
        print(f"  Changed Pixel Ratio:  {pct_str}")
        print(f"  Example Sample Paths:")
        for s, paths in res["sample_paths"].items():
            print(f"    [{s}]:")
            for k, p in paths.items():
                print(f"       {k}: {p}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

