"""Effect of test-time augmentation and radiometric alignment on the existing OSCD checkpoint (no retraining).

Thresholds are chosen on the 3 validation pairs for each option; the 10 official test pairs are only scored.
"""
import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oscd_lib import evaluate, load_model, load_split  # noqa: E402

ML = Path(__file__).resolve().parent.parent
ckpt = Path(sys.argv[1]) if len(sys.argv) > 1 else ML / "experiments" / "oscd_finetune" / "best_model.pth"
dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
train_all, test = load_split("train"), load_split("test")
val = [p for i, p in enumerate(train_all) if i in (3, 7, 12)]
model = load_model(ckpt, dev)
out = {}
for name, kw in [("plain", dict(tta=False, match=False)), ("histogram_match", dict(tta=False, match=True)), ("tta8", dict(tta=True, match=False)), ("tta8+match", dict(tta=True, match=True))]:
    r = evaluate([model], test, dev, ref_pairs=val, **kw)
    out[name] = r
    print(f"{name:16s} F1 {r['f1']:.3f} IoU {r['change_iou']:.3f} P {r['precision']:.3f} R {r['recall']:.3f} thr {r['threshold']}", flush=True)
(ML / "experiments" / "oscd_finetune" / "inference_options.json").write_text(json.dumps(out, indent=2))
