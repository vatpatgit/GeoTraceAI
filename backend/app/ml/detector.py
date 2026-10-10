"""Tiled, overlap-blended, georeferenced inference for the Siamese ResNet50-UNet change detector."""
from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Callable

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window
from scipy import ndimage

from app.config import settings
from app.geo.config import DetectionConfig
from app.geo.detect import SCORE_NODATA, DetectionOutput, _write_score
from app.geo.errors import PairIncompatibleError
from app.geo.preprocess import AlignedPair
from app.ml.registry import ModelCard, ensure_ml_path, get_card, learned_ready

ProgressFn = Callable[[float, str], None]
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_MODEL_CACHE: dict[tuple[str, str], object] = {}
_CACHE_LOCK = threading.Lock()


def resolve_device(pref: str = "auto"):
    import torch

    pref = settings.ML_DEVICE if pref == "auto" else pref
    if pref == "cuda" and not torch.cuda.is_available():
        raise PairIncompatibleError("CUDA was requested but is not available on this machine.", code="cuda_unavailable")
    if pref == "auto":
        pref = "cuda" if torch.cuda.is_available() else "cpu"
    return torch.device(pref)


def load_model(card: ModelCard, device):
    """Load (and cache) the network. ``weights_only=True`` and ``strict=True`` guard against bad checkpoints."""
    import torch

    key = (card.id, str(device))
    with _CACHE_LOCK:
        if key in _MODEL_CACHE:
            return _MODEL_CACHE[key]
        if not ensure_ml_path():
            raise PairIncompatibleError("The ML model code (ML/terratrack) is not available on this server.", code="model_unavailable")
        from terratrack.models.siamese_unet import SiameseResNetUNet

        if not card.weights_path.is_file():
            raise PairIncompatibleError(f"Model weights for '{card.id}' are not installed.", code="model_unavailable")
        try:
            ckpt = torch.load(card.weights_path, map_location="cpu", weights_only=True)
            if card.arch == "idasiamnet":
                from terratrack.models.idasiamnet import IDASiamNet

                model = IDASiamNet(pretrained_weights=None)  # weights come from the checkpoint; nothing is downloaded
            else:
                model = SiameseResNetUNet(pretrained=False)  # never downloads ImageNet weights
            model.load_state_dict(ckpt["model_state_dict"], strict=True)
        except Exception as exc:  # incompatible / corrupt checkpoint
            raise PairIncompatibleError(f"Model checkpoint '{card.id}' could not be loaded: {exc}", code="model_incompatible") from exc
        model.to(device).eval()
        for p in model.parameters():
            p.requires_grad_(False)
        _MODEL_CACHE[key] = model
        return model


def _ramp_weights(size: int, ramp: int) -> np.ndarray:
    w1 = np.ones(size, dtype=np.float32)
    if ramp > 0:
        r = (np.arange(ramp, dtype=np.float32) + 1) / (ramp + 1)
        w1[:ramp] = r
        w1[-ramp:] = r[::-1]
    return np.outer(w1, w1).astype(np.float32)


def _stretch_params(aligned: AlignedPair, rgb_idx: list[int]) -> tuple[np.ndarray, np.ndarray] | None:
    """Joint (both-dates) percentile stretch for >8-bit data so both images share one radiometric mapping."""
    with rasterio.open(aligned.before_path) as db, rasterio.open(aligned.after_path) as da, rasterio.open(aligned.valid_mask_path) as dm:
        if db.dtypes[0] == "uint8" and da.dtypes[0] == "uint8":
            return None
        step = max(1, int(math.ceil(math.sqrt(db.width * db.height / 2_000_000))))
        shape = (max(1, db.height // step), max(1, db.width // step))
        m = dm.read(1, out_shape=shape, resampling=Resampling.nearest) > 0
        lo, hi = np.zeros(3, np.float32), np.ones(3, np.float32)
        for k, bi in enumerate(rgb_idx):
            vals = np.concatenate([
                db.read(bi, out_shape=shape, resampling=Resampling.nearest)[m],
                da.read(bi, out_shape=shape, resampling=Resampling.nearest)[m],
            ]).astype(np.float32)
            lo[k], hi[k] = np.percentile(vals, [2, 98])
            if hi[k] - lo[k] < 1e-6:
                hi[k] = lo[k] + 1.0
        return lo, hi


def detect_learned(aligned: AlignedPair, cfg: DetectionConfig, out_dir: str | Path, progress: ProgressFn | None = None,
                   cancel_check: Callable[[], bool] | None = None) -> DetectionOutput:
    import torch

    report = progress or (lambda f, m: None)
    card = get_card(cfg.model_id)
    if card is None or not learned_ready(cfg.model_id):
        raise PairIncompatibleError(
            "No trained change-detection model is installed on this server. Use the spectral baseline method, or install "
            "weights with ML/scripts/export_for_backend.py.", code="model_unavailable")
    if not {"red", "green", "blue"} <= set(aligned.roles):
        raise PairIncompatibleError("The learned model needs red, green and blue bands.", code="model_bands_missing")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    device = resolve_device(cfg.device)
    model = load_model(card, device)
    use_amp = device.type == "cuda"

    rgb_idx = [aligned.roles.index(r) + 1 for r in ("red", "green", "blue")]
    stretch = _stretch_params(aligned, rgb_idx)
    ts = cfg.tile_size
    overlap = min(cfg.tile_overlap, ts // 2)
    target_gsd = cfg.target_gsd_m or card.trained_gsd_m
    scale = target_gsd / aligned.pixel_size_m  # native pixels per model pixel
    win_native = max(8, int(round(ts * scale)))
    stride_native = max(1, int(round((ts - overlap) * scale)))
    h, w = aligned.height, aligned.width

    notes: list[str] = []
    gsd_ratio = aligned.pixel_size_m / card.trained_gsd_m
    if not 0.25 <= gsd_ratio <= 2.0:
        notes.append(
            f"Input ground resolution ({aligned.pixel_size_m:.2f} m) differs from the ~{card.trained_gsd_m:g} m the model was trained at; "
            "imagery is rescaled to that scale, but results on this resolution/sensor have NOT been validated.")
    notes.extend(card.limitations[:2])

    rows = list(range(0, max(h - win_native, 0) + 1, stride_native))
    cols = list(range(0, max(w - win_native, 0) + 1, stride_native))
    if rows[-1] + win_native < h:
        rows.append(h - win_native)
    if cols[-1] + win_native < w:
        cols.append(w - win_native)
    rows = sorted(set(max(0, r) for r in rows))
    cols = sorted(set(max(0, c) for c in cols))
    total = len(rows) * len(cols)

    prob_sum = np.zeros((h, w), dtype=np.float32)
    wt_sum = np.zeros((h, w), dtype=np.float32)
    weights_model = _ramp_weights(ts, overlap)
    batch_size = 8 if device.type == "cuda" else 2

    with rasterio.open(aligned.before_path) as db, rasterio.open(aligned.after_path) as da, rasterio.open(aligned.valid_mask_path) as dm:
        valid_full = dm.read(1).astype(bool)

        def prep(ds, win: Window) -> np.ndarray:
            arr = ds.read(rgb_idx, window=win, out_shape=(3, ts, ts), boundless=True, fill_value=0,
                          resampling=Resampling.average if scale > 1.5 else Resampling.bilinear).astype(np.float32)
            if stretch is None:
                arr = arr / 255.0
            else:
                lo, hi = stretch
                arr = np.clip((arr - lo[:, None, None]) / (hi - lo)[:, None, None], 0, 1)
            arr = (arr - IMAGENET_MEAN[:, None, None]) / IMAGENET_STD[:, None, None]
            return arr

        pending: list[tuple[Window, np.ndarray, np.ndarray]] = []
        done = 0

        def flush():
            nonlocal pending
            if not pending:
                return
            t1 = torch.from_numpy(np.stack([p[1] for p in pending])).to(device, non_blocking=True)
            t2 = torch.from_numpy(np.stack([p[2] for p in pending])).to(device, non_blocking=True)
            with torch.inference_mode():
                with torch.autocast(device_type=device.type, enabled=use_amp):
                    logits = model(t1, t2)
                probs = torch.sigmoid(logits.float())[:, 0].cpu().numpy()
            for (win, _, _), p in zip(pending, probs):
                # restore model tile -> native window size
                zoom = (win.height / ts, win.width / ts)
                p_native = ndimage.zoom(p, zoom, order=1) if abs(zoom[0] - 1) > 1e-6 else p
                w_native = ndimage.zoom(weights_model, zoom, order=1) if abs(zoom[0] - 1) > 1e-6 else weights_model
                r0, c0 = int(win.row_off), int(win.col_off)
                rh = min(p_native.shape[0], h - r0)
                cw = min(p_native.shape[1], w - c0)
                prob_sum[r0:r0 + rh, c0:c0 + cw] += (p_native * w_native)[:rh, :cw]
                wt_sum[r0:r0 + rh, c0:c0 + cw] += w_native[:rh, :cw]
            pending = []

        for r in rows:
            for c in cols:
                if cancel_check and cancel_check():
                    from app.geo.pipeline import JobCancelled
                    raise JobCancelled()
                win = Window(c, r, win_native, win_native)
                vwin = valid_full[r:r + win_native, c:c + win_native]
                done += 1
                if not vwin.any():
                    continue  # nothing valid in this tile: skip the (expensive) forward pass
                pending.append((win, prep(db, win), prep(da, win)))
                if len(pending) >= batch_size:
                    flush()
                    report(0.05 + 0.9 * done / total, f"Model inference {done}/{total} tiles")
        flush()

    prob = np.divide(prob_sum, wt_sum, out=np.zeros_like(prob_sum), where=wt_sum > 0)
    threshold = float(cfg.model_threshold if cfg.model_threshold is not None else card.threshold)
    score = prob.astype(np.float32)
    score[~valid_full] = SCORE_NODATA
    score_path = out / "change_score.tif"
    _write_score(score_path, score, aligned)
    report(0.98, "Model inference complete")
    return DetectionOutput(
        method="learned_siamese", score_path=str(score_path), score_threshold=threshold,
        category_basis="model_inferred", default_category=card.category,
        magnitude_kind="model_probability", confidence_kind="model_probability_uncalibrated",
        details={"model_id": card.id, "model_name": card.name, "device": str(device), "mixed_precision": use_amp,
                 "tile_size": ts, "tile_overlap": overlap, "tiles": total, "target_gsd_m": target_gsd,
                 "native_window_px": win_native, "threshold": threshold, "model_sha256": card.sha256,
                 "model_metrics_heldout": card.metrics.get("test")},
        notes=notes,
    )
