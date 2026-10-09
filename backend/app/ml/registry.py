"""Model registry: cards describing the available trained checkpoints, with verified metrics and limitations."""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings


@dataclass
class ModelCard:
    id: str
    name: str
    weights_path: Path
    threshold: float
    category: str
    dataset: str
    description: str
    architecture: str
    trained_gsd_m: float
    metrics: dict[str, Any] = field(default_factory=dict)
    metrics_note: str = ""
    limitations: list[str] = field(default_factory=list)
    sha256: str | None = None
    bands: tuple[str, ...] = ("red", "green", "blue")

    @property
    def available(self) -> bool:
        return self.weights_path.is_file()

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "dataset": self.dataset, "category": self.category,
            "description": self.description, "architecture": self.architecture, "threshold": self.threshold,
            "trained_gsd_m": self.trained_gsd_m, "metrics": self.metrics, "metrics_note": self.metrics_note,
            "limitations": self.limitations, "available": self.available, "bands": list(self.bands),
            "sha256": self.sha256,
        }


def registry_path() -> Path:
    return Path(settings.MODEL_DIR) / "registry.json"


def load_cards() -> tuple[str | None, dict[str, ModelCard]]:
    p = registry_path()
    if not p.is_file():
        return None, {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    cards: dict[str, ModelCard] = {}
    for m in raw.get("models", []):
        cards[m["id"]] = ModelCard(
            id=m["id"], name=m["name"], weights_path=Path(settings.MODEL_DIR) / m["weights"],
            threshold=float(m["threshold"]), category=m.get("category", "change"), dataset=m.get("dataset", ""),
            description=m.get("description", ""), architecture=m.get("architecture", ""),
            trained_gsd_m=float(m.get("input", {}).get("trained_gsd_m", 2.0)), metrics=m.get("metrics", {}),
            metrics_note=m.get("metrics_note", ""), limitations=list(m.get("limitations", [])), sha256=m.get("sha256"),
            bands=tuple(m.get("input", {}).get("bands", ["red", "green", "blue"])),
        )
    return raw.get("default"), cards


def get_card(model_id: str | None = None) -> ModelCard | None:
    default, cards = load_cards()
    mid = model_id or default
    return cards.get(mid) if mid else None


def torch_available() -> bool:
    return importlib.util.find_spec("torch") is not None


def ensure_ml_path() -> bool:
    """Make the ``terratrack`` model package importable. Returns False when the ML sources are not present."""
    root = Path(settings.ML_ROOT)
    if not (root / "terratrack" / "models" / "siamese_unet.py").is_file():
        return False
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return True


def learned_ready(model_id: str | None = None) -> bool:
    """True only if torch is importable, the model code exists and the checkpoint file is on disk."""
    if not torch_available() or not ensure_ml_path():
        return False
    card = get_card(model_id)
    return bool(card and card.available)
