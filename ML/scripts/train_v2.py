"""Improved OSCD training for the Siamese ResNet50-UNet with cross-validated model selection.

    python ML/scripts/train_v2.py --name v2_aux --aux 0.3 --epochs 12

Protocol (honest model selection on a tiny dataset):
  1. 3-fold cross-validation over the 14 OSCD *training* pairs. Every fold trains from the same starting checkpoint; out-of-fold
     probabilities are pooled, so epoch and decision threshold are chosen on all 14 pairs without ever scoring a pair with a model
     that saw it.
  2. A final model is trained on all 14 pairs for the selected number of epochs.
  3. The 10 official OSCD *test* pairs are scored exactly once with that model and the pooled out-of-fold threshold.

Improvements over scripts/finetune_oscd.py: exponential moving average of the weights (the old run peaked at epoch 5 of 60 and then
degraded), radiometric alignment of the two dates (histogram matching, also used at inference), random-scale and noise
augmentation, optional mixing of degraded high-resolution urban-change pairs (LEVIR-CD) as a regulariser, and 8-way
test-time augmentation.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oscd_lib import best_threshold, load_model, load_split, match_histogram, predict_models, score, to_input  # noqa: E402

ML_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML_ROOT))
from terratrack.losses.change_losses import BCEDiceLoss  # noqa: E402
from terratrack.models.siamese_unet import SiameseResNetUNet  # noqa: E402
from finetune_oscd import jitter  # noqa: E402


# ------------------------------------------------------------------------------------------------------------------ data
def load_levir(n: int, seed: int):
    root = ML_ROOT / "datasets" / "LEVIR-CD" / "train"
    names = sorted(p.name for p in (root / "A").glob("*.png"))
    random.Random(seed).shuffle(names)
    out = []
    for nm in names[:n]:
        a = np.asarray(Image.open(root / "A" / nm).convert("RGB"))
        b = np.asarray(Image.open(root / "B" / nm).convert("RGB"))
        m = (np.asarray(Image.open(root / "label" / nm).convert("L")) > 127).astype(np.uint8)
        out.append((a, b, m))
    return out


def degrade_crop(a, b, m, rng: random.Random, size: int = 256):
    """Turn a 0.5 m aerial pair into a coarse (~1-3 m) pair: crop a (size*f)^2 window, box-downsample by f, blur lightly, add noise."""
    f = rng.uniform(2.0, 5.0)
    win = int(size * f)
    h, w = m.shape
    win = min(win, h, w)
    y0, x0 = rng.randrange(h - win + 1), rng.randrange(w - win + 1)
    crops = [x[y0:y0 + win, x0:x0 + win] for x in (a, b)]
    mm = m[y0:y0 + win, x0:x0 + win]
    out = []
    for im in crops:
        p = Image.fromarray(im).resize((size, size), Image.BOX)
        if rng.random() < 0.5:
            p = p.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.0)))
        out.append(np.asarray(p))
    mk = np.asarray(Image.fromarray(mm * 255).resize((size, size), Image.BOX)) > 100
    return out[0], out[1], mk.astype(np.uint8)


class Sampler(torch.utils.data.Dataset):
    def __init__(self, pairs, aux, n: int, aux_p: float, size: int = 256, seed: int = 0):
        self.pairs, self.aux, self.n, self.aux_p, self.size, self.rng = pairs, aux, n, aux_p, size, random.Random(seed)

    def __len__(self):
        return self.n

    def _oscd_crop(self):
        rng, s = self.rng, self.size
        a, b, m = self.pairs[rng.randrange(len(self.pairs))]
        sc = rng.uniform(0.75, 1.5) if rng.random() < 0.5 else 1.0  # random scale: tolerance to the preview resolution the app feeds
        if sc != 1.0:
            h, w = m.shape
            nh, nw = max(int(h * sc), s), max(int(w * sc), s)
            a = np.asarray(Image.fromarray(a).resize((nw, nh), Image.BILINEAR))
            b = np.asarray(Image.fromarray(b).resize((nw, nh), Image.BILINEAR))
            m = np.asarray(Image.fromarray(m * 255).resize((nw, nh), Image.NEAREST)) > 127
            m = m.astype(np.uint8)
        h, w = m.shape
        if rng.random() < 0.6 and m.any():
            ys, xs = np.nonzero(m)
            k = rng.randrange(len(ys))
            y0 = int(np.clip(ys[k] - rng.randrange(s), 0, max(h - s, 0)))
            x0 = int(np.clip(xs[k] - rng.randrange(s), 0, max(w - s, 0)))
        else:
            y0, x0 = rng.randrange(max(h - s, 0) + 1), rng.randrange(max(w - s, 0) + 1)
        a, b, m = a[y0:y0 + s, x0:x0 + s], b[y0:y0 + s, x0:x0 + s], m[y0:y0 + s, x0:x0 + s]
        if a.shape[0] < s or a.shape[1] < s:
            ph, pw = s - a.shape[0], s - a.shape[1]
            a, b = np.pad(a, ((0, ph), (0, pw), (0, 0))), np.pad(b, ((0, ph), (0, pw), (0, 0)))
            m = np.pad(m, ((0, ph), (0, pw)))
        return a, b, m

    def __getitem__(self, i):
        rng = self.rng
        if self.aux and rng.random() < self.aux_p:
            a, b, m = degrade_crop(*self.aux[rng.randrange(len(self.aux))], rng, self.size)
        else:
            a, b, m = self._oscd_crop()
        k = rng.randrange(4)
        a, b, m = np.rot90(a, k), np.rot90(b, k), np.rot90(m, k)
        if rng.random() < 0.5:
            a, b, m = a[:, ::-1], b[:, ::-1], m[:, ::-1]
        if rng.random() < 0.5:
            a, b = b, a
        a, b = np.ascontiguousarray(a), np.ascontiguousarray(b)
        a, b = jitter(a, rng), jitter(b, rng)
        if rng.random() < 0.7:  # inference aligns the dates radiometrically, so most training pairs are aligned too
            b = match_histogram(b, a)
        if rng.random() < 0.3:
            noise = np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(1, 5), a.shape)
            a = np.clip(a + noise, 0, 255).astype(np.uint8)
        return torch.from_numpy(to_input(a)), torch.from_numpy(to_input(b)), torch.from_numpy(np.ascontiguousarray(m)[None].astype(np.float32))


# ------------------------------------------------------------------------------------------------------------------ training
class EMA:
    def __init__(self, model, decay: float):
        self.m, self.d = copy.deepcopy(model).eval(), decay
        for p in self.m.parameters():
            p.requires_grad_(False)

    @torch.no_grad()
    def update(self, model):
        for e, p in zip(self.m.state_dict().values(), model.state_dict().values()):
            if e.dtype.is_floating_point:
                e.mul_(self.d).add_(p.detach(), alpha=1 - self.d)
            else:
                e.copy_(p)


ARCH = "siamese_unet"


def new_model(init: Path, device):
    if ARCH == "idasiamnet":
        from terratrack.models.idasiamnet import IDASiamNet
        m = IDASiamNet(pretrained_weights=None)
    else:
        m = SiameseResNetUNet(pretrained=False)
    m.load_state_dict(torch.load(init, map_location="cpu", weights_only=False)["model_state_dict"], strict=True)
    return m.to(device)


def param_groups(model, lr_enc: float, lr_dec: float):
    """Pretrained encoder at the low rate, everything else (decoder / interaction / fusion head) at the high one."""
    if ARCH == "idasiamnet":
        enc = [p for n, p in model.named_parameters() if n.startswith(("stem", "layers"))]
        rest = [p for n, p in model.named_parameters() if not n.startswith(("stem", "layers"))]
    else:
        enc, rest = list(model.encoder.parameters()), list(model.decoder.parameters())
    return [{"params": enc, "lr": lr_enc}, {"params": rest, "lr": lr_dec}]


def train_epochs(model, ema, sampler, epochs: int, args, device, on_epoch):
    crit = BCEDiceLoss(bce_weight=0.5, dice_weight=0.5, pos_weight=3.0).to(device)
    opt = torch.optim.AdamW(param_groups(model, args.lr_enc, args.lr_dec), weight_decay=1e-4)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    for ep in range(1, epochs + 1):
        model.train()
        loader = torch.utils.data.DataLoader(sampler, batch_size=args.batch, num_workers=0)
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
            ema.update(model)
            tot += loss.item()
        on_epoch(ep, tot / len(loader))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--arch", default="siamese_unet", choices=["siamese_unet", "idasiamnet"])
    ap.add_argument("--init", default=str(ML_ROOT / "experiments" / "levir-cd_baseline" / "best_model.pth"))
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--aux", type=float, default=0.0, help="share of each batch drawn from degraded LEVIR-CD pairs")
    ap.add_argument("--aux_pairs", type=int, default=120)
    ap.add_argument("--lr_enc", type=float, default=2e-5)
    ap.add_argument("--lr_dec", type=float, default=2e-4)
    ap.add_argument("--ema", type=float, default=0.93)
    ap.add_argument("--eval_epochs", default="3,5,7,9,12")
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    global ARCH
    ARCH = args.arch
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out = ML_ROOT / "experiments" / args.name
    out.mkdir(parents=True, exist_ok=True)
    train_all, test = load_split("train"), load_split("test")
    aux = load_levir(args.aux_pairs, args.seed) if args.aux > 0 else []
    eval_eps = sorted({int(x) for x in args.eval_epochs.split(",") if int(x) <= args.epochs} | {args.epochs})
    print(f"device={device} pairs={len(train_all)} test={len(test)} aux={len(aux)} eval_epochs={eval_eps}", flush=True)
    t0 = time.time()

    # ---- 1. cross-validation: out-of-fold probabilities at the evaluation epochs (EMA weights, TTA + radiometric alignment)
    folds = [[i for i in range(len(train_all)) if i % args.folds == k] for k in range(args.folds)]
    oof = {ep: {} for ep in eval_eps}
    for k, hold in enumerate(folds):
        tr = [p for i, p in enumerate(train_all) if i not in hold]
        model = new_model(Path(args.init), device)
        ema = EMA(model, args.ema)
        sampler = Sampler(tr, aux, args.iters * args.batch, args.aux, seed=args.seed + k)

        def on_epoch(ep, loss, hold=hold, ema=ema):
            if ep in eval_eps:
                for i in hold:
                    oof[ep][i] = predict_models([ema.m], train_all[i][0], train_all[i][1], device, tta=True, match=True)
                print(f"  fold {k + 1}/{args.folds} epoch {ep:02d} loss {loss:.4f} ({time.time() - t0:.0f}s)", flush=True)

        train_epochs(model, ema, sampler, args.epochs, args, device, on_epoch)
        del model, ema
        torch.cuda.empty_cache()

    cv = {}
    for ep in eval_eps:
        idx = sorted(oof[ep])
        bt = best_threshold([oof[ep][i] for i in idx], [train_all[i][2] for i in idx])
        cv[ep] = bt
        print(f"CV epoch {ep:02d}: pooled out-of-fold F1 {bt['f1']:.3f} IoU {bt['change_iou']:.3f} P {bt['precision']:.3f} R {bt['recall']:.3f} thr {bt['threshold']}", flush=True)
    best_ep = max(cv, key=lambda e: cv[e]["f1"])
    thr = cv[best_ep]["threshold"]
    print(f"selected epoch {best_ep}, threshold {thr}", flush=True)

    # ---- 2. final model on all 14 pairs for the selected number of epochs
    model = new_model(Path(args.init), device)
    ema = EMA(model, args.ema)
    sampler = Sampler(train_all, aux, args.iters * args.batch, args.aux, seed=args.seed + 99)
    train_epochs(model, ema, sampler, best_ep, args, device, lambda ep, loss: print(f"  final epoch {ep:02d} loss {loss:.4f}", flush=True))

    # ---- 3. the untouched test pairs, scored once
    tm = [p[2] for p in test]
    res = {"name": args.name, "args": vars(args), "cv": {str(e): v for e, v in cv.items()}, "selected_epoch": best_ep, "threshold": thr, "test": {}}
    for label, kw in (("plain", dict(tta=False, match=False)), ("match+tta8", dict(tta=True, match=True))):
        probs = [predict_models([ema.m], a, b, device, **kw) for a, b, _ in test]
        r = score(probs, tm, thr)
        r["per_pair_f1"] = [round(score([p], [m], thr)["f1"], 3) for p, m in zip(probs, tm)]
        res["test"][label] = r
        print(f"TEST {label:11s} F1 {r['f1']:.3f} IoU {r['change_iou']:.3f} P {r['precision']:.3f} R {r['recall']:.3f} (threshold {thr} from cross-validation)", flush=True)
    torch.save({"epoch": best_ep, "model_state_dict": ema.m.state_dict(), "best_threshold": float(thr), "metrics": {k: float(v) for k, v in res["test"]["match+tta8"].items() if k in ("precision", "recall", "f1", "change_iou")},
                "config": {"dataset": "OSCD", "init": str(args.init), "aux": args.aux, "recipe": "train_v2", "arch": args.arch}}, out / "best_model.pth")
    (out / "results.json").write_text(json.dumps(res, indent=2))
    print(f"done in {time.time() - t0:.0f}s -> {out}", flush=True)


if __name__ == "__main__":
    main()
