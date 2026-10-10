"""Shared helpers for the OSCD experiments: radiometric alignment, dihedral test-time augmentation, ensembles and scoring."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finetune_oscd import best_threshold, load_model, load_split, score, to_input  # noqa: E402,F401


def match_histogram(src: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Per-channel quantile mapping of ``src`` onto the distribution of ``ref`` (removes date-to-date illumination / season / processing offsets)."""
    out = np.empty_like(src)
    for c in range(src.shape[2]):
        s, r = src[..., c].ravel(), ref[..., c].ravel()
        sv, si, sc = np.unique(s, return_inverse=True, return_counts=True)
        rv, rc = np.unique(r, return_counts=True)
        sq = (np.cumsum(sc) - 0.5 * sc) / s.size
        rq = (np.cumsum(rc) - 0.5 * rc) / r.size
        out[..., c] = np.interp(sq, rq, rv)[si].reshape(src.shape[:2]).astype(src.dtype)
    return out


def _dihedral(x: torch.Tensor, k: int, flip: bool) -> torch.Tensor:
    x = torch.rot90(x, k, (2, 3))
    return torch.flip(x, (3,)) if flip else x


def _undo(x: torch.Tensor, k: int, flip: bool) -> torch.Tensor:
    if flip:
        x = torch.flip(x, (3,))
    return torch.rot90(x, -k, (2, 3))


@torch.no_grad()
def predict_models(models, a: np.ndarray, b: np.ndarray, device, tile: int = 256, stride: int = 128, tta: bool = True, match: bool = False,
                   scale: float = 1.0) -> np.ndarray:
    """Probability map averaged over models and (optionally) the 8 dihedral transforms; ``match`` aligns image b's radiometry to a first."""
    if match:
        b = match_histogram(b, a)
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
    ops = [(k, f) for f in (False, True) for k in range(4)] if tta else [(0, False)]
    for r in rows:
        for c in cols:
            t1 = torch.from_numpy(to_input(ap[r:r + tile, c:c + tile]))[None].to(device)
            t2 = torch.from_numpy(to_input(bp[r:r + tile, c:c + tile]))[None].to(device)
            b1 = torch.cat([_dihedral(t1, k, f) for k, f in ops])
            b2 = torch.cat([_dihedral(t2, k, f) for k, f in ops])
            p = 0.0
            for m in models:
                with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                    lo = torch.sigmoid(m(b1, b2).float())
                p = p + torch.stack([_undo(lo[i:i + 1], k, f)[0, 0] for i, (k, f) in enumerate(ops)]).mean(0)
            acc[r:r + tile, c:c + tile] += (p / len(models)).cpu().numpy()
            cnt[r:r + tile, c:c + tile] += 1
    prob = (acc / cnt)[:H, :W]
    if scale != 1.0:
        prob = np.asarray(Image.fromarray(prob).resize((w, h), Image.BILINEAR))
    return prob


def evaluate(models, pairs, device, thr: float | None = None, ref_pairs=None, **kw) -> dict:
    """F1 etc. on ``pairs``. The threshold is taken from ``ref_pairs`` (validation) when given, never tuned on ``pairs`` itself."""
    masks = [p[2] for p in pairs]
    probs = [predict_models(models, a, b, device, **kw) for a, b, _ in pairs]
    if thr is None and ref_pairs is not None:
        rp = [predict_models(models, a, b, device, **kw) for a, b, _ in ref_pairs]
        thr = best_threshold(rp, [p[2] for p in ref_pairs])["threshold"]
    if thr is None:
        thr = best_threshold(probs, masks)["threshold"]
    r = score(probs, masks, thr)
    r["per_pair_f1"] = [round(score([p], [m], thr)["f1"], 3) for p, m in zip(probs, masks)]
    return r
