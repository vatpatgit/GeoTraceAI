"""Learned-detector integration: missing weights, CPU smoke test, tiling/georeferencing, and a real-checkpoint check."""
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio

torch = pytest.importorskip("torch")

from app.config import settings
from app.geo.config import DetectionConfig, PipelineConfig
from app.geo.errors import PairIncompatibleError
from app.geo.pipeline import run_pipeline
from app.geo.preprocess import align_pair
from app.geo.synthetic import ChangeSpec, make_synthetic_pair
from app.ml import detector as det_mod
from app.ml import registry as reg
from app.ml.registry import ensure_ml_path

pytestmark = pytest.mark.skipif(not ensure_ml_path(), reason="ML/terratrack sources not present")


def _write_registry(model_dir: Path, model_id: str, weights: Path | None, threshold: float = 0.5):
    entry = {"id": model_id, "name": "random-weights test model", "weights": f"{model_id}.pt", "threshold": threshold,
             "category": "building_change", "dataset": "none", "input": {"trained_gsd_m": 2.0, "bands": ["red", "green", "blue"]},
             "metrics": {}, "limitations": ["test fixture"], "architecture": "SiameseResNetUNet"}
    (model_dir / "registry.json").write_text(json.dumps({"default": model_id, "models": [entry]}), encoding="utf-8")


@pytest.fixture
def fake_model(tmp_path, monkeypatch):
    """A structurally valid but randomly initialised checkpoint (exercises plumbing, not accuracy)."""
    from terratrack.models.siamese_unet import SiameseResNetUNet

    mid = f"fake-{tmp_path.name[-8:]}"
    torch.manual_seed(0)
    net = SiameseResNetUNet(pretrained=False)
    torch.save({"model_state_dict": net.state_dict(), "threshold": 0.5}, tmp_path / f"{mid}.pt")
    _write_registry(tmp_path, mid, tmp_path / f"{mid}.pt")
    monkeypatch.setattr(settings, "MODEL_DIR", tmp_path)
    det_mod._MODEL_CACHE.clear()
    yield mid, net
    det_mod._MODEL_CACHE.clear()


@pytest.fixture
def rgb_pair(tmp_path):
    return make_synthetic_pair(tmp_path / "rgb", shape=(300, 300), pixel_size=2.0, rgb_only=True, dtype="uint8", seed=5,
                               changes=(ChangeSpec("built", (100, 160), (100, 180)),), speckle=0, name="rgb")


def test_missing_checkpoint_is_reported_not_crashed(tmp_path, monkeypatch, rgb_pair):
    monkeypatch.setattr(settings, "MODEL_DIR", tmp_path / "does-not-exist")
    assert reg.learned_ready() is False
    cfg = PipelineConfig(detection=DetectionConfig(method="learned_siamese"))
    with pytest.raises(PairIncompatibleError) as err:
        run_pipeline(rgb_pair.before, rgb_pair.after, tmp_path / "w", cfg)
    assert err.value.code == "model_unavailable"
    # 'auto' must degrade to the baseline instead of failing
    res = run_pipeline(rgb_pair.before, rgb_pair.after, tmp_path / "w2", PipelineConfig())
    assert res.detection.method == "spectral_cva" and "no trained checkpoint" in res.method_reason


def test_corrupt_checkpoint_is_rejected_with_clear_error(tmp_path, monkeypatch, rgb_pair):
    (tmp_path / "bad-v1.pt").write_bytes(b"not a torch file")
    _write_registry(tmp_path, "bad-v1", None)
    monkeypatch.setattr(settings, "MODEL_DIR", tmp_path)
    det_mod._MODEL_CACHE.clear()
    aligned = align_pair(rgb_pair.before, rgb_pair.after, tmp_path / "al")
    with pytest.raises(PairIncompatibleError) as err:
        det_mod.detect_learned(aligned, DetectionConfig(method="learned_siamese", device="cpu"), tmp_path / "d")
    assert err.value.code == "model_incompatible"


def test_cpu_inference_is_georeferenced_and_covers_every_valid_pixel(fake_model, rgb_pair, tmp_path):
    mid, _ = fake_model
    aligned = align_pair(rgb_pair.before, rgb_pair.after, tmp_path / "al")
    cfg = DetectionConfig(method="learned_siamese", model_id=mid, device="cpu", target_gsd_m=2.0)
    out = det_mod.detect_learned(aligned, cfg, tmp_path / "d")
    assert out.method == "learned_siamese" and out.confidence_kind == "model_probability_uncalibrated"
    assert out.details["device"] == "cpu" and out.details["mixed_precision"] is False
    with rasterio.open(out.score_path) as sc, rasterio.open(aligned.before_path) as ref, rasterio.open(aligned.valid_mask_path) as vm:
        assert sc.crs == ref.crs and sc.transform == ref.transform and (sc.width, sc.height) == (ref.width, ref.height)
        s, v = sc.read(1), vm.read(1) > 0
    assert np.all(np.isfinite(s))
    assert np.all((s[v] > 0) & (s[v] < 1))  # every valid pixel was scored by at least one tile (sigmoid of random logits)
    assert np.all(s[~v] == -1.0)


def test_single_tile_matches_direct_forward_pass(fake_model, tmp_path):
    """When the raster is exactly one model tile, tiled inference must equal a plain forward pass."""
    mid, net = fake_model
    pair = make_synthetic_pair(tmp_path / "p", shape=(256, 256), pixel_size=2.0, rgb_only=True, dtype="uint8", seed=9,
                               changes=(ChangeSpec("built", (80, 140), (80, 140)),), speckle=0, name="t")
    aligned = align_pair(pair.before, pair.after, tmp_path / "al")
    assert (aligned.width, aligned.height) == (256, 256)
    out = det_mod.detect_learned(aligned, DetectionConfig(model_id=mid, device="cpu", target_gsd_m=2.0), tmp_path / "d")

    def load(p):
        with rasterio.open(p) as ds:
            a = ds.read([1, 2, 3]).astype(np.float32) / 255.0
        return ((a - det_mod.IMAGENET_MEAN[:, None, None]) / det_mod.IMAGENET_STD[:, None, None])[None]

    net.eval()
    with torch.no_grad():
        direct = torch.sigmoid(net(torch.from_numpy(load(aligned.before_path)), torch.from_numpy(load(aligned.after_path))))[0, 0].numpy()
    with rasterio.open(out.score_path) as sc:
        tiled = sc.read(1)
    assert np.abs(tiled - direct).max() < 1e-3


def test_scale_matching_reads_coarser_pixels_at_model_gsd(fake_model, tmp_path):
    """0.5 m imagery is shown to the model at ~2 m: native windows are 4x larger than the model tile."""
    mid, _ = fake_model
    pair = make_synthetic_pair(tmp_path / "hi", shape=(640, 640), pixel_size=0.5, rgb_only=True, dtype="uint8", seed=2,
                               changes=(ChangeSpec("built", (200, 300), (200, 300)),), speckle=0, name="hi")
    aligned = align_pair(pair.before, pair.after, tmp_path / "al")
    out = det_mod.detect_learned(aligned, DetectionConfig(model_id=mid, device="cpu", target_gsd_m=2.0), tmp_path / "d")
    assert out.details["native_window_px"] == 1024  # 256 model px * (2.0 m / 0.5 m)
    assert out.details["tiles"] >= 1
    with rasterio.open(out.score_path) as sc:
        s = sc.read(1)
    assert s.shape == (640, 640) and np.all(s > 0)


def test_coarse_imagery_triggers_out_of_distribution_warning(fake_model, tmp_path):
    mid, _ = fake_model
    pair = make_synthetic_pair(tmp_path / "s2", shape=(128, 128), pixel_size=10.0, rgb_only=True, dtype="uint8", seed=4,
                               changes=(), speckle=0, name="s2")
    aligned = align_pair(pair.before, pair.after, tmp_path / "al")
    out = det_mod.detect_learned(aligned, DetectionConfig(model_id=mid, device="cpu"), tmp_path / "d")
    assert any("NOT been validated" in n for n in out.notes)


# ------------------------------------------------------------------------------------------------------------------
# Real trained checkpoint on real LEVIR-CD pairs, run through the *georeferenced tiled* path.
# ------------------------------------------------------------------------------------------------------------------
LEVIR_VAL = Path(settings.ML_ROOT) / "datasets" / "LEVIR-CD" / "val"
REAL_WEIGHTS = Path(settings.MODEL_DIR) / "levir-cd-v1.pt"


@pytest.mark.slow
@pytest.mark.skipif(not (LEVIR_VAL.exists() and REAL_WEIGHTS.exists()), reason="LEVIR-CD data / exported weights not installed")
def test_real_checkpoint_detects_real_building_changes(tmp_path):
    from PIL import Image
    from rasterio.transform import Affine
    from app.geo.writers import write_geotiff

    det_mod._MODEL_CACHE.clear()
    names = sorted(p.name for p in (LEVIR_VAL / "A").glob("*.png"))[:12]
    tp = fp = fn = 0
    for i, name in enumerate(names):
        label = np.array(Image.open(LEVIR_VAL / "label" / name).convert("L")) > 127
        if label.sum() < 2000:
            continue  # need a meaningful amount of change for a stable F1
        tr = Affine(0.5, 0, 500000, 0, -0.5, 4500000)  # 0.5 m pixels, UTM 33N
        paths = {}
        for k, folder in (("before", "A"), ("after", "B")):
            arr = np.array(Image.open(LEVIR_VAL / folder / name).convert("RGB")).transpose(2, 0, 1)
            paths[k] = write_geotiff(tmp_path / f"{i}_{k}.tif", arr, crs="EPSG:32633", transform=tr,
                                     descriptions=["red", "green", "blue"], build_overviews=False)
        res = run_pipeline(paths["before"], paths["after"], tmp_path / f"w{i}",
                           PipelineConfig(detection=DetectionConfig(method="learned_siamese", model_id="levir-cd-v1")))
        assert res.detection.method == "learned_siamese"
        with rasterio.open(res.mask_path) as ds:
            pred = ds.read(1) == 1
        assert pred.shape == label.shape
        tp += int((pred & label).sum()); fp += int((pred & ~label).sum()); fn += int((~pred & label).sum())
        assert all(f.confidence is not None and 0 <= f.confidence <= 1 for f in res.features)
    assert tp + fn > 0, "no usable LEVIR samples"
    f1 = 2 * tp / (2 * tp + fp + fn)
    # The checkpoint's held-out test F1 is 0.726 at 256px; the georeferenced native-scale path with post-processing
    # must be in the same regime (we require a conservative floor, not the headline number).
    print(f"\nREAL-CHECKPOINT PIPELINE F1={f1:.3f} tp={tp} fp={fp} fn={fn} on {len(names)} candidate LEVIR val tiles")
    assert f1 > 0.55, f"F1 {f1:.3f} (tp={tp}, fp={fp}, fn={fn})"
