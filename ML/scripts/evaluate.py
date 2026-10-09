"""Evaluate a trained change-detection checkpoint on a dataset split.

The threshold is NOT tuned here. By default the threshold stored in the checkpoint
(chosen on the validation split during training) is applied unchanged, so running
this on the ``test`` split yields an honest held-out estimate.

Example:
    python scripts/evaluate.py --checkpoint experiments/levir-cd_baseline/best_model.pth \
        --dataset LEVIR-CD --split test --out experiments/levir-cd_baseline/eval_test.json
"""

import argparse
import json
import sys
from pathlib import Path

ml_root = Path(__file__).resolve().parent.parent
if str(ml_root) not in sys.path:
    sys.path.insert(0, str(ml_root))

import numpy as np
import torch
from torch.utils.data import DataLoader

from terratrack.datasets.base import PairedTransform
from terratrack.datasets.levir_cd import LEVIRCDAdapter
from terratrack.datasets.s2looking import S2LookingAdapter
from terratrack.datasets.second import SECONDAdapter
from terratrack.datasets.sysu_cd import SYSUCDAdapter
from terratrack.evaluation.metrics import compute_metrics
from terratrack.models.siamese_unet import SiameseResNetUNet

DATASET_ROOTS = {
    "levir-cd": ("datasets/LEVIR-CD", LEVIRCDAdapter),
    "s2looking": ("datasets/S2Looking/S2Looking", S2LookingAdapter),
    "second": ("datasets/second_dataset", SECONDAdapter),
    "sysu-cd": ("datasets/SYSU-CD", SYSUCDAdapter),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--dataset", required=True, choices=["LEVIR-CD", "S2Looking", "SECOND", "SYSU-CD"])
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--threshold", type=float, default=None, help="Override threshold (default: checkpoint's)")
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    threshold = args.threshold if args.threshold is not None else float(ckpt.get("best_threshold", 0.5))

    model = SiameseResNetUNet(pretrained=False)
    model.load_state_dict(ckpt["model_state_dict"], strict=True)
    model.to(device).eval()

    root_rel, adapter = DATASET_ROOTS[args.dataset.lower()]
    transform = PairedTransform(target_size=(args.image_size, args.image_size), is_train=False)
    dataset = adapter(ml_root / root_rel, split=args.split, transform=transform)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)

    tp = fp = fn = tn = 0
    with torch.no_grad():
        for batch in loader:
            t1 = batch["image_t1"].to(device)
            t2 = batch["image_t2"].to(device)
            target = batch["mask"].numpy()
            prob = torch.sigmoid(model(t1, t2)).cpu().numpy()
            m = compute_metrics((prob >= threshold).astype(np.uint8).ravel(), target.ravel())
            tp += m["tp"]; fp += m["fp"]; fn += m["fn"]; tn += m["tn"]

    eps = 1e-7
    precision = tp / (tp + fp + eps)
    recall = tp / (tp + fn + eps)
    f1 = 2 * precision * recall / (precision + recall + eps)
    change_iou = tp / (tp + fp + fn + eps)
    result = {
        "checkpoint": str(args.checkpoint),
        "checkpoint_epoch": int(ckpt.get("epoch", -1)),
        "dataset": args.dataset,
        "split": args.split,
        "num_samples": len(dataset),
        "image_size": args.image_size,
        "threshold": threshold,
        "device": device.type,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "change_iou": change_iou,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }
    print(json.dumps(result, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
