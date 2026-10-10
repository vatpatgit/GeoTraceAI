"""Train the IDA-SiamNet style network (terratrack/models/idasiamnet.py) on LEVIR-CD and evaluate on the official test split.

    python ML/scripts/train_idasiamnet_levir.py --iters 12000

Protocol: train on ``LEVIR-CD/train`` (445 pairs of 1024x1024), choose the checkpoint and the decision threshold on ``val`` (64 pairs),
score ``test`` (128 pairs) once at the end with whole-image inference. Metrics are pixel-level precision / recall / F1 / IoU of the
change class (the standard LEVIR-CD protocol). Augmentation follows the reference configuration: random rotation / flip, random crop
biased towards changed pixels, time exchange (swap the two dates) and photometric distortion.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ML_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML_ROOT))
from terratrack.losses.change_losses import BCEDiceLoss  # noqa: E402
from terratrack.models.idasiamnet import IDASiamNet  # noqa: E402

ROOT = ML_ROOT / "datasets" / "LEVIR-CD"
MEAN = np.array([0.485, 0.456, 0.406], np.float32)[:, None, None]
STD = np.array([0.229, 0.224, 0.225], np.float32)[:, None, None]


def to_tensor(img: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(((img.astype(np.float32) / 255.0).transpose(2, 0, 1) - MEAN) / STD)


def names(split: str):
    return sorted(p.name for p in (ROOT / split / "A").glob("*.png"))


def load(split: str, name: str):
    a = np.asarray(Image.open(ROOT / split / "A" / name).convert("RGB"))
    b = np.asarray(Image.open(ROOT / split / "B" / name).convert("RGB"))
    m = (np.asarray(Image.open(ROOT / split / "label" / name).convert("L")) > 127).astype(np.uint8)
    return a, b, m


def photometric(img: np.ndarray, rng: random.Random) -> np.ndarray:
    x = img.astype(np.float32)
    if rng.random() < 0.5:
        x = x + rng.uniform(-10, 10)
    if rng.random() < 0.5:
        x = (x - 127.5) * rng.uniform(0.8, 1.2) + 127.5
    if rng.random() < 0.5:  # saturation
        g = x.mean(2, keepdims=True)
        x = g + (x - g) * rng.uniform(0.8, 1.2)
    return np.clip(x, 0, 255).astype(np.uint8)


class LevirTrain(torch.utils.data.Dataset):
    def __init__(self, n: int, crop: int, seed: int):
        self.names, self.n, self.crop, self.seed = names("train"), n, crop, seed

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        rng = random.Random(self.seed * 1_000_003 + i)
        a, b, m = load("train", self.names[rng.randrange(len(self.names))])
        s = self.crop
        for _ in range(8):  # like cat_max_ratio: avoid crops that are almost all one class, and favour changed pixels
            if rng.random() < 0.6 and m.any():
                ys, xs = np.nonzero(m)
                k = rng.randrange(len(ys))
                y0 = int(np.clip(ys[k] - rng.randrange(s), 0, m.shape[0] - s))
                x0 = int(np.clip(xs[k] - rng.randrange(s), 0, m.shape[1] - s))
            else:
                y0, x0 = rng.randrange(m.shape[0] - s + 1), rng.randrange(m.shape[1] - s + 1)
            mc = m[y0:y0 + s, x0:x0 + s]
            if mc.mean() < 0.75 or mc.any():
                break
        a, b, m = a[y0:y0 + s, x0:x0 + s], b[y0:y0 + s, x0:x0 + s], mc
        k = rng.randrange(4)
        a, b, m = np.rot90(a, k), np.rot90(b, k), np.rot90(m, k)
        if rng.random() < 0.5:
            a, b, m = a[:, ::-1], b[:, ::-1], m[:, ::-1]
        if rng.random() < 0.5:  # time exchange
            a, b = b, a
        a, b = photometric(np.ascontiguousarray(a), rng), photometric(np.ascontiguousarray(b), rng)
        return to_tensor(a), to_tensor(b), torch.from_numpy(np.ascontiguousarray(m)[None].astype(np.float32))


@torch.no_grad()
def predict_split(model, split: str, device, limit: int | None = None):
    model.eval()
    probs, masks = [], []
    for nm in names(split)[:limit]:
        a, b, m = load(split, nm)
        with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
            p = torch.sigmoid(model(to_tensor(a)[None].to(device), to_tensor(b)[None].to(device)).float())[0, 0].cpu().numpy()
        probs.append(p.astype(np.float16)); masks.append(m)
    return probs, masks


def score(probs, masks, thr: float) -> dict:
    tp = fp = fn = 0
    for p, m in zip(probs, masks):
        pr = p >= thr
        tp += int(np.sum(pr & (m > 0))); fp += int(np.sum(pr & (m == 0))); fn += int(np.sum(~pr & (m > 0)))
    prec, rec = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return {"precision": prec, "recall": rec, "f1": 2 * prec * rec / max(prec + rec, 1e-9), "change_iou": tp / max(tp + fp + fn, 1), "threshold": thr}


def best_threshold(probs, masks):
    return max((score(probs, masks, round(t, 2)) for t in np.arange(0.2, 0.81, 0.05)), key=lambda r: r["f1"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=12000)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--crop", type=int, default=256)
    ap.add_argument("--lr_backbone", type=float, default=1e-4)
    ap.add_argument("--lr_head", type=float, default=1e-3)
    ap.add_argument("--eval_every", type=int, default=1500)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(ML_ROOT / "experiments" / "idasiamnet_levir"))
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args()
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    model = IDASiamNet().to(device)
    bb = [p for n, p in model.named_parameters() if n.startswith(("stem", "layers"))]
    head = [p for n, p in model.named_parameters() if not n.startswith(("stem", "layers"))]
    opt = torch.optim.AdamW([{"params": bb, "lr": args.lr_backbone, "base": args.lr_backbone}, {"params": head, "lr": args.lr_head, "base": args.lr_head}], weight_decay=0.01)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    crit = BCEDiceLoss(bce_weight=0.5, dice_weight=0.5, pos_weight=2.0).to(device)
    start, best, log = 0, {"f1": -1.0}, []
    if args.resume and (out / "last.pth").is_file():
        ck = torch.load(out / "last.pth", map_location="cpu", weights_only=False)
        model.load_state_dict(ck["model"]); opt.load_state_dict(ck["opt"]); start, best, log = ck["iter"], ck["best"], ck["log"]
        print(f"resumed at iteration {start}, best val F1 {best['f1']:.4f}", flush=True)
    print(f"device={device} params={sum(p.numel() for p in model.parameters()) / 1e6:.1f}M train={len(names('train'))} val={len(names('val'))} test={len(names('test'))} iters={args.iters}", flush=True)

    ds = LevirTrain((args.iters - start) * args.batch, args.crop, args.seed + start)
    loader = torch.utils.data.DataLoader(ds, batch_size=args.batch, num_workers=args.workers, persistent_workers=args.workers > 0, prefetch_factor=4 if args.workers else None)
    t0, run_loss, it = time.time(), 0.0, start
    model.train()
    for t1, t2, y in loader:
        it += 1
        warm = min(1.0, it / 300)
        decay = (1 - it / args.iters) ** 0.9
        for g in opt.param_groups:
            g["lr"] = g["base"] * warm * decay
        t1, t2, y = t1.to(device, non_blocking=True), t2.to(device, non_blocking=True), y.to(device, non_blocking=True)
        opt.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
            loss = crit(model(t1, t2), y)
        scaler.scale(loss).backward()
        scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        scaler.step(opt); scaler.update()
        run_loss += loss.item()
        if it % 100 == 0:
            print(f"iter {it:6d} loss {run_loss / 100:.4f} lr {opt.param_groups[1]['lr']:.2e} ({time.time() - t0:.0f}s)", flush=True)
            run_loss = 0.0
        if it % args.eval_every == 0 or it == args.iters:
            vp, vm = predict_split(model, "val", device)
            bt = best_threshold(vp, vm)
            log.append({"iter": it, **{k: float(v) for k, v in bt.items()}})
            flag = ""
            if bt["f1"] > best["f1"]:
                best = {**bt, "iter": it}
                torch.save({"epoch": it, "model_state_dict": model.state_dict(), "best_threshold": float(bt["threshold"]), "metrics": {k: float(v) for k, v in bt.items()},
                            "config": {"dataset": "LEVIR-CD", "arch": "IDASiamNet", "backbone": "resnet50", "crop": args.crop}}, out / "best_model.pth")
                flag = "  (best)"
            torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "iter": it, "best": best, "log": log}, out / "last.pth")
            print(f"== iter {it}: val F1 {bt['f1']:.4f} IoU {bt['change_iou']:.4f} P {bt['precision']:.4f} R {bt['recall']:.4f} thr {bt['threshold']}{flag}", flush=True)
            model.train()

    # ---- the official test split, scored once with the checkpoint and threshold chosen on validation
    final = IDASiamNet(pretrained_weights=None).to(device)
    final.load_state_dict(torch.load(out / "best_model.pth", map_location="cpu", weights_only=False)["model_state_dict"])
    tp_, tm_ = predict_split(final, "test", device)
    res = {"dataset": "LEVIR-CD", "model": "IDASiamNet (ResNet50, local ImageNet weights)", "iters": args.iters, "best_val": best,
           "test": score(tp_, tm_, best["threshold"]), "val_log": log, "args": vars(args)}
    res["test"]["num_samples"] = len(tm_)
    (out / "results.json").write_text(json.dumps(res, indent=2))
    r = res["test"]
    print(f"TEST (128 official pairs): F1 {r['f1']:.4f} IoU {r['change_iou']:.4f} P {r['precision']:.4f} R {r['recall']:.4f} thr {r['threshold']}  [{time.time() - t0:.0f}s]", flush=True)


if __name__ == "__main__":
    main()
