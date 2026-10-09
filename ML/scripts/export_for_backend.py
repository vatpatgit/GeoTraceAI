"""Export weights-only checkpoints + model cards for the GeoTrace backend.

Training checkpoints contain optimizer state (~527 MB). The backend only needs the weights (~176 MB) and a model
card holding the *reproduced* held-out metrics (run ``scripts/evaluate.py`` first so ``eval_test.json`` exists).

    python scripts/export_for_backend.py --out ../backend/models
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ml_root = Path(__file__).resolve().parent.parent
if str(ml_root) not in sys.path:
    sys.path.insert(0, str(ml_root))

import torch

from terratrack.models.siamese_unet import SiameseResNetUNet

# experiment folder -> card template. Metrics are read from eval_*.json produced by scripts/evaluate.py.
MODELS = {
    "levir-cd_baseline": {
        "id": "levir-cd-v1",
        "name": "Siamese ResNet50-UNet - LEVIR-CD (building change)",
        "dataset": "LEVIR-CD",
        "category": "building_change",
        "description": "Trained on 0.5 m aerial imagery of US cities (1024px tiles resized to 256px, ~2 m effective).",
    },
    "s2looking_baseline": {
        "id": "s2looking-v1",
        "name": "Siamese ResNet50-UNet - S2Looking (rural building change)",
        "dataset": "S2Looking",
        "category": "building_change",
        "description": "Trained on 0.5-0.8 m side-looking satellite imagery of rural areas (resized to 256px).",
    },
    "second_baseline": {
        "id": "second-v1",
        "name": "Siamese ResNet50-UNet - SECOND (land-cover change)",
        "dataset": "SECOND",
        "category": "land_cover_change",
        "description": "Binary 'any land-cover class changed' target derived from SECOND semantic labels (512px resized to 256px).",
    },
    "oscd_finetune": {
        "id": "oscd-s2-v1",
        "name": "Siamese ResNet50-UNet - OSCD fine-tune (Sentinel-2 urban change)",
        "dataset": "OSCD",
        "category": "urban_change",
        "description": ("LEVIR-CD checkpoint fine-tuned on 11 real Sentinel-2 city pairs (RGB, 10 m) of the Onera Satellite Change "
                        "Detection dataset; fed at 10 m/px."),
        "gsd_m": 10.0,
        "results": "results.json",
        "limitations": [
            "Fine-tuned on only 11 image pairs (24 in the whole OSCD dataset); expect weak generalisation to other regions, seasons and land covers.",
            "Trained to find URBAN change (new buildings and roads) in RGB Sentinel-2 imagery; it is not a vegetation, flood, fire or crop-change detector.",
            "Validated on the 10 official OSCD test pairs only (see metrics); no validation on your area of interest.",
            "Output probabilities are not calibrated; do not read them as confidence in a statistical sense.",
            "A detection is an observed appearance change, not proof of construction, damage or illegal activity. Clouds, haze, shadows and seasonal colour shifts can produce false detections.",
        ],
    },
}

LIMITATIONS = [
    "Trained on RGB aerial/very-high-resolution imagery down-sampled to ~2 m ground resolution.",
    "NOT validated on Sentinel-2 (10 m) or any other medium-resolution sensor; expect degraded results there.",
    "Output probabilities are not calibrated; do not read them as confidence in a statistical sense.",
    "A detection is an observed appearance change, not proof of construction, damage or illegal activity.",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ml_root.parent / "backend" / "models"))
    parser.add_argument("--default", default="levir-cd-v1", help="model used by generic (auto) analyses; the Compare-dates tool prefers oscd-s2-v1")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cards = []
    for exp, meta in MODELS.items():
        src = ml_root / "experiments" / exp / "best_model.pth"
        if not src.exists():
            print(f"[skip] {exp}: no best_model.pth")
            continue
        ckpt = torch.load(src, map_location="cpu", weights_only=True)
        model = SiameseResNetUNet(pretrained=False)
        model.load_state_dict(ckpt["model_state_dict"], strict=True)  # fail loudly on architecture drift
        weights = out / f"{meta['id']}.pt"
        torch.save({"model_state_dict": model.state_dict(), "architecture": "SiameseResNetUNet/abs_diff",
                    "threshold": float(ckpt.get("best_threshold", 0.5)), "epoch": int(ckpt.get("epoch", -1))}, weights)

        metrics = {}
        note = ("Held-out 'test' split numbers were measured by scripts/evaluate.py at the checkpoint's own "
                "threshold (selected on the validation split). 'val' numbers are optimistic.")
        if meta.get("results"):  # OSCD fine-tune: metrics come from finetune_oscd.py, including zero-shot and spectral baselines
            res = json.loads((ml_root / "experiments" / exp / meta["results"]).read_text(encoding="utf-8"))
            ft = res["finetuned"]
            metrics["test"] = {"num_samples": res["splits"]["test"], "threshold": ft["threshold"], "precision": ft["precision"], "recall": ft["recall"],
                               "f1": ft["f1"], "change_iou": ft["change_iou"]}
            metrics["val"] = {"num_samples": res["splits"]["val"], "threshold": ft["threshold"], **ft["val"]}
            z = res["zero_shot_scale_1"]; c = res["spectral_cva_baseline"]
            note = (f"Pixel-level metrics on the {res['splits']['test']} official OSCD test pairs (whole images, 10 m), threshold chosen on "
                    f"{res['splits']['val']} validation pairs. For comparison on the same pairs: the starting checkpoint (zero-shot) F1 {z['f1']:.2f}, "
                    f"spectral change-vector baseline F1 {c['f1']:.2f}. Small test set (10 scenes): treat differences of a few points as noise.")
        for split in ("test", "val"):
            if meta.get("results"):
                break
            ev = ml_root / "experiments" / exp / f"eval_{split}.json"
            if ev.exists():
                e = json.loads(ev.read_text(encoding="utf-8"))
                metrics[split] = {k: e[k] for k in ("num_samples", "threshold", "precision", "recall", "f1", "change_iou")}
        cards.append({
            **{k: v for k, v in meta.items() if k not in ("gsd_m", "results", "limitations")},
            "weights": weights.name,
            "sha256": sha256(weights),
            "architecture": "Siamese ResNet50 (shared encoder) + |F1-F2| multi-scale difference + U-Net decoder",
            "parameters_millions": round(sum(p.numel() for p in model.parameters()) / 1e6, 2),
            "input": {"bands": ["red", "green", "blue"], "normalisation": "imagenet", "tile_size": 256, "trained_gsd_m": meta.get("gsd_m", 2.0)},
            "threshold": float(ckpt.get("best_threshold", 0.5)),
            "trained_epoch": int(ckpt.get("epoch", -1)),
            "metrics": metrics,
            "metrics_note": note,
            "limitations": meta.get("limitations", LIMITATIONS),
        })
        print(f"[ok] {exp} -> {weights.name} ({weights.stat().st_size / 1e6:.0f} MB)")

    registry = {"default": args.default, "models": cards}
    (out / "registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    print(f"wrote {out / 'registry.json'} with {len(cards)} model(s)")


if __name__ == "__main__":
    main()
