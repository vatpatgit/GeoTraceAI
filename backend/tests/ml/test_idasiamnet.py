"""IDA-SiamNet: architecture contract, registry card and loading through the backend detector."""
import pytest

torch = pytest.importorskip("torch")

from app.config import settings  # noqa: E402
from app.ml.registry import get_card, learned_ready  # noqa: E402


def _net():
    from app.ml.registry import ensure_ml_path
    assert ensure_ml_path()
    from terratrack.models.idasiamnet import IDASiamNet
    return IDASiamNet(pretrained_weights=None)


def test_forward_contract_and_symmetric_inputs_accepted():
    net = _net().eval()
    a, b = torch.randn(2, 3, 128, 128), torch.randn(2, 3, 128, 128)
    with torch.no_grad():
        out = net(a, b)
        assert out.shape == (2, 1, 128, 128) and torch.isfinite(out).all()  # one logit per pixel at input size
        assert net(a, a).shape == out.shape


def test_interaction_modules_exchange_information_between_dates():
    from terratrack.models.idasiamnet import CEFI, SEFI
    x1, x2 = torch.randn(2, 8, 16, 16), torch.randn(2, 8, 16, 16)
    for m in (SEFI(), CEFI(8)):
        a1, a2 = m(x1, x2)
        b1, _ = m(x1, torch.randn_like(x2))
        assert a1.shape == x1.shape and not torch.allclose(a1, b1)  # date-1 output depends on date 2


def test_registry_card_declares_architecture_and_honest_scope():
    card = get_card("idasiamnet-levir-v1")
    if card is None:
        pytest.skip("IDA-SiamNet is not registered on this machine")
    assert card.arch == "idasiamnet" and card.trained_gsd_m == 0.5 and card.metrics["test"]["num_samples"] == 128
    assert any("NOT validated on Sentinel-2" in x for x in card.limitations)


@pytest.mark.skipif(not (settings.MODEL_DIR / "idasiamnet-levir-v1.pt").is_file(), reason="weights not installed")
def test_checkpoint_loads_strictly_through_the_detector_loader():
    from app.ml.detector import load_model, resolve_device
    assert learned_ready("idasiamnet-levir-v1")
    model = load_model(get_card("idasiamnet-levir-v1"), resolve_device("cpu"))
    assert type(model).__name__ == "IDASiamNet" and not any(p.requires_grad for p in model.parameters())
