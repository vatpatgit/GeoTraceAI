"""Fine-tune the Siamese ResNet50-UNet on OSCD (real Sentinel-2 change pairs at 10 m) and evaluate it honestly.

    python ML/scripts/finetune_oscd.py [--init ML/experiments/levir-cd_baseline/best_model.pth] [--epochs 60]

Data: ``ML/datasets/OSCD_RGB`` (parquet mirror of the Onera Satellite Change Detection dataset; 14 train + 10 test city pairs,
RGB, 10 m). Splits: 11 train / 3 validation pairs (the validation pairs choose the epoch and the decision threshold) and the
10 official test pairs, which are touched exactly once at the end. Zero-shot baselines (the starting checkpoint, and a simple
spectral change-vector baseline) are evaluated on the same test pairs so the improvement - or lack of it - is measurable.

Outputs ``ML/experiments/oscd_finetune/`` : best_model.pth, results.json, training_log.csv.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import torch
import torch.nn.functional as F
from PIL import Image

ML_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML_ROOT))

from terratrack.losses.change_losses import BCEDiceLoss  # noqa: E402
from terratrack.models.siamese_unet import SiameseResNetUNet  # noqa: E402

MEAN = np.array([0.485, 0.456, 0.406], np.float32)[:, None, None]
STD = np.array([0.229, 0.224, 0.225], np.float32)[:, None, None]
VAL_IDX = (3, 7, 12)  # train-split pair indices held out for validation (different cities / sizes)


def load_split(split: str):
    t = pq.read_table(ML_ROOT / "datasets" / "OSCD_RGB" / "data" / f"{split}-00000-of-00001.parquet").to_pylist()
    out = []
    for r in t:
        a = np.asarray(Image.open(io.BytesIO(r["image1"]["bytes"])).convert("RGB"))
        b = np.asarray(Image.open(io.BytesIO(r["image2"]["bytes"])).convert("RGB"))
        m = (np.asarray(Image.open(io.BytesIO(r["mask"]["bytes"]))) > 0).astype(np.uint8)
        out.append((a, b, m))
    return out


def to_input(img_u8: np.ndarray) -> np.ndarray:
    x = img_u8.astype(np.float32).transpose(2, 0, 1) / 255.0
    return (x - MEAN) / STD


def jitter(img: np.ndarray, rng: random.Random) -> np.ndarray:
    """Independent radiometric jitter per date (sun angle / season / sensor processing differ between dates and between products)."""
    x = img.astype(np.float32) / 255.0
    x = np.clip(x, 0, 1) ** rng.uniform(0.75, 1.35)
    x = x * rng.uniform(0.75, 1.3) + rng.uniform(-0.06, 0.06)
    x = x * np.array([rng.uniform(0.92, 1.08) for _ in range(3)], np.float32)
    return (np.clip(x, 0, 1) * 255).astype(np.uint8)


class CropSampler(torch.utils.data.Dataset):
    def __init__(self, pairs, n: int, size: int = 256, seed: int = 0):
        self.pairs, self.n, self.size, self.rng = pairs, n, size, random.Random(seed)

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        rng = self.rng
        a, b, m = self.pairs[rng.randrange(len(self.pairs))]
        h, w = m.shape
        s = self.size
        if rng.random() < 0.6 and m.any():  # centre half of the crops on a changed pixel so the rare class is seen
            ys, xs = np.nonzero(m)
            k = rng.randrange(len(ys))
            y0 = int(np.clip(ys[k] - rng.randrange(s), 0, max(h - s, 0)))
            x0 = int(np.clip(xs[k] - rng.randrange(s), 0, max(w - s, 0)))
        else:
            y0, x0 = rng.randrange(max(h - s, 0) + 1), rng.randrange(max(w - s, 0) + 1)
        a, b, m = a[y0:y0 + s, x0:x0 + s], b[y0:y0 + s, x0:x0 + s], m[y0:y0 + s, x0:x0 + s]
        if a.shape[0] < s or a.shape[1] < s:  # tiny image: pad
            ph, pw = s - a.shape[0], s - a.shape[1]
            a, b = np.pad(a, ((0, ph), (0, pw), (0, 0))), np.pad(b, ((0, ph), (0, pw), (0, 0)))
            m = np.pad(m, ((0, ph), (0, pw)))
        k = rng.randrange(4)
        a, b, m = np.rot90(a, k), np.rot90(b, k), np.rot90(m, k)
        if rng.random() < 0.5:
            a, b, m = a[:, ::-1], b[:, ::-1], m[:, ::-1]
        if rng.random() < 0.5:
            a, b = b, a  # change is symmetric in time
        a, b = jitter(np.ascontiguousarray(a), rng), jitter(np.ascontiguousarray(b), rng)
        return torch.from_numpy(to_input(a)), torch.from_numpy(to_input(b)), torch.from_numpy(np.ascontiguousarray(m)[None].astype(np.float32))


@torch.no_grad()
def predict_full(model, a: np.ndarray, b: np.ndarray, device, tile: int = 256, stride: int = 128, scale: float = 1.0) -> np.ndarray:
    """Sliding-window probability map at the image's native resolution (optionally rescaled by ``scale`` before the network)."""
    h, w, _ = a.shape
    if scale != 1.0:
        a = np.asarray(Image.fromarray(a).resize((int(w * scale), int(h * scale)), Image.BILINEAR))
        b = np.asarray(Image.fromarray(b).resize((int(w * scale), int(h * scale)), Image.BILINEAR))
    H, W, _ = a.shape
    ph, pw = max(tile - H, 0), max(tile - W, 0)
    ap, bp = np.pad(a, ((0, ph), (0, pw), (0, 0)), mode="reflect"), np.pad(b, ((0, ph), (0, pw), (0, 0)), mode="reflect")
    HH, WW = ap.shape[:2]
    acc, cnt = np.zeros((HH, WW), np.float32), np.zeros((HH, WW), np.float32)
    rows = sorted(set(list(range(0, HH - tile + 1, stride)) + [HH - tile]))
    cols = sorted(set(list(range(0, WW - tile + 1, stride)) + [WW - tile]))
    for r in rows:
        for c in cols:
            t1 = torch.from_numpy(to_input(ap[r:r + tile, c:c + tile]))[None].to(device)
            t2 = torch.from_numpy(to_input(bp[r:r + tile, c:c + tile]))[None].to(device)
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                p = torch.sigmoid(model(t1, t2).float())[0, 0].cpu().numpy()
            acc[r:r + tile, c:c + tile] += p
            cnt[r:r + tile, c:c + tile] += 1
    prob = (acc / cnt)[:H, :W]
    if scale != 1.0:
        prob = np.asarray(Image.fromarray(prob).resize((w, h), Image.BILINEAR))
    return prob


def score(probs, masks, thr: float) -> dict:
    tp = fp = fn = 0
    for p, m in zip(probs, masks):
        pr = p >= thr
        tp += int(np.sum(pr & (m > 0)))
        fp += int(np.sum(pr & (m == 0)))
        fn += int(np.sum(~pr & (m > 0)))
    prec, rec = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return {"precision": prec, "recall": rec, "f1": 2 * prec * rec / max(prec + rec, 1e-9), "change_iou": tp / max(tp + fp + fn, 1), "threshold": thr}


def best_threshold(probs, masks):
    cands = [round(t, 2) for t in np.arange(0.10, 0.96, 0.05)]
    res = [score(probs, masks, t) for t in cands]
    return max(res, key=lambda r: r["f1"])


def cva_baseline(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Spectral change-vector magnitude (after per-band median/MAD matching), scaled to 0..1 by a robust z-score."""
    x, y = a.astype(np.float32), b.astype(np.float32)
    y = (y - np.median(y, axis=(0, 1))) / (np.median(np.abs(y - np.median(y, axis=(0, 1))), axis=(0, 1)) + 1e-6) * (np.median(np.abs(x - np.median(x, axis=(0, 1))), axis=(0, 1)) + 1e-6) + np.median(x, axis=(0, 1))
    mag = np.sqrt(((x - y) ** 2).sum(-1))
    z = (mag - np.median(mag)) / (1.4826 * np.median(np.abs(mag - np.median(mag))) + 1e-6)
    return np.clip(z / 12.0, 0, 1)


def load_model(path: Path | None, device):
    model = SiameseResNetUNet(pretrained=False)
    if path is not None:
        ck = torch.load(path, map_location="cpu", weights_only=False)
        model.load_state_dict(ck["model_state_dict"], strict=True)
    return model.to(device).eval()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", default=str(ML_ROOT / "experiments" / "levir-cd_baseline" / "best_model.pth"))
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--iters", type=int, default=40, help="batches per epoch")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--out", default=str(ML_ROOT / "experiments" / "oscd_finetune"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    train_all, test = load_split("train"), load_split("test")
    train = [p for i, p in enumerate(train_all) if i not in VAL_IDX]
    val = [p for i, p in enumerate(train_all) if i in VAL_IDX]
    print(f"device={device} train_pairs={len(train)} val_pairs={len(val)} test_pairs={len(test)}")
    vm, tm = [p[2] for p in val], [p[2] for p in test]

    results: dict = {"dataset": "OSCD (Sentinel-2, RGB, 10 m)", "splits": {"train": len(train), "val": len(val), "test": len(test)}, "init_checkpoint": str(args.init)}

    # ---- zero-shot baselines on the (untouched) test pairs, thresholds picked on validation only
    base = load_model(Path(args.init), device)
    for scale in (1.0, 5.0):
        vp = [predict_full(base, a, b, device, scale=scale) for a, b, _ in val]
        th = best_threshold(vp, vm)["threshold"]
        tp_ = [predict_full(base, a, b, device, scale=scale) for a, b, _ in test]
        results[f"zero_shot_scale_{scale:g}"] = {**score(tp_, tm, th), "note": f"starting checkpoint, imagery fed at {10 / scale:g} m/px"}
    vp = [cva_baseline(a, b) for a, b, _ in val]
    th = best_threshold(vp, vm)["threshold"]
    results["spectral_cva_baseline"] = score([cva_baseline(a, b) for a, b, _ in test], tm, th)
    del base
    print(json.dumps({k: v for k, v in results.items() if isinstance(v, dict) and "f1" in v}, indent=1))

    # ---- fine-tune
    model = SiameseResNetUNet(pretrained=False)
    model.load_state_dict(torch.load(args.init, map_location="cpu", weights_only=False)["model_state_dict"], strict=True)
    model.to(device)
    crit = BCEDiceLoss(bce_weight=0.5, dice_weight=0.5, pos_weight=3.0).to(device)
    opt = torch.optim.AdamW([{"params": model.encoder.parameters(), "lr": 2e-5}, {"params": model.decoder.parameters(), "lr": 2e-4}], weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs, eta_min=1e-6)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    ds = CropSampler(train, n=args.iters * args.batch, seed=args.seed)
    log = out / "training_log.csv"
    with open(log, "w", newline="") as f:
        csv.writer(f).writerow(["epoch", "train_loss", "val_f1", "val_iou", "val_threshold", "seconds"])
    best = {"f1": -1.0}
    t0 = time.time()
    for ep in range(1, args.epochs + 1):
        model.train()
        loader = torch.utils.data.DataLoader(ds, batch_size=args.batch, num_workers=0)
        tot = 0.0
        for t1, t2, y in loader:
            t1, t2, y = t1.to(device), t2.to(device), y.to(device)
            opt.zero_grad()
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                loss = crit(model(t1, t2), y)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt); scaler.update()
            tot += loss.item()
        sched.step()
        model.eval()
        vp = [predict_full(model, a, b, device) for a, b, _ in val]
        bt = best_threshold(vp, vm)
        with open(log, "a", newline="") as f:
            csv.writer(f).writerow([ep, round(tot / len(loader), 4), round(bt["f1"], 4), round(bt["change_iou"], 4), bt["threshold"], round(time.time() - t0)])
        flag = ""
        if bt["f1"] > best["f1"]:
            best = {**bt, "epoch": ep}
            torch.save({"epoch": ep, "model_state_dict": model.state_dict(), "best_threshold": float(bt["threshold"]), "metrics": {k: float(v) for k, v in bt.items()}, "config": {"dataset": "OSCD", "init": str(args.init)}}, out / "best_model.pth")
            flag = " (best)"
        print(f"epoch {ep:03d} loss {tot / len(loader):.4f} val F1 {bt['f1']:.3f} IoU {bt['change_iou']:.3f} thr {bt['threshold']}{flag}")

    # ---- final: best checkpoint on the untouched test pairs
    final = load_model(out / "best_model.pth", device)
    tp_ = [predict_full(final, a, b, device) for a, b, _ in test]
    results["finetuned"] = {**score(tp_, tm, best["threshold"]), "best_epoch": best["epoch"], "val": {k: best[k] for k in ("precision", "recall", "f1", "change_iou")},
                            "note": "threshold and epoch chosen on the 3 validation pairs; test pairs used once"}
    results["per_pair_test_f1"] = [round(score([p], [m], best["threshold"])["f1"], 3) for p, m in zip(tp_, tm)]
    (out / "results.json").write_text(json.dumps(results, indent=2))
    print("\nTEST RESULTS (10 official OSCD test pairs)")
    for k in ("zero_shot_scale_1", "zero_shot_scale_5", "spectral_cva_baseline", "finetuned"):
        r = results[k]
        print(f"  {k:24s} F1 {r['f1']:.3f}  IoU {r['change_iou']:.3f}  P {r['precision']:.3f}  R {r['recall']:.3f}  thr {r['threshold']}")


if __name__ == "__main__":
    main()
