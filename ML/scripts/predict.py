"""Inference and change prediction script."""

import argparse
import sys
from pathlib import Path

# Add ML root directory to sys.path
ml_root = Path(__file__).resolve().parent.parent
if str(ml_root) not in sys.path:
    sys.path.insert(0, str(ml_root))

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
import torch
import torchvision.transforms.functional as TF

from terratrack.models.siamese_unet import SiameseResNetUNet


def predict_pair(
    t1_path: str | Path,
    t2_path: str | Path,
    checkpoint_path: str | Path,
    output_path: str | Path,
    image_size: int = 256,
    threshold: float = 0.50,
    device: str = "cuda",
):
    dev = torch.device(device if torch.cuda.is_available() and device == "cuda" else "cpu")
    print(f"Loading checkpoint from: {checkpoint_path} onto {dev}")
    
    ckpt = torch.load(checkpoint_path, map_location=dev)
    state = ckpt.get("model_state_dict", ckpt)
    thresh = ckpt.get("best_threshold", threshold)

    model = SiameseResNetUNet(pretrained=False)
    model.load_state_dict(state)
    model.to(dev)
    model.eval()

    img1 = Image.open(t1_path).convert("RGB")
    img2 = Image.open(t2_path).convert("RGB")
    orig_w, orig_h = img1.size

    # Transform
    img1_res = TF.resize(img1, (image_size, image_size))
    img2_res = TF.resize(img2, (image_size, image_size))

    t1_t = TF.normalize(TF.to_tensor(img1_res), [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]).unsqueeze(0).to(dev)
    t2_t = TF.normalize(TF.to_tensor(img2_res), [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]).unsqueeze(0).to(dev)

    with torch.no_grad():
        logits = model(t1_t, t2_t)
        probs = torch.sigmoid(logits)[0, 0].cpu().numpy()

    # Resize probability map back to original input resolution
    prob_img = Image.fromarray((probs * 255).astype(np.uint8)).resize((orig_w, orig_h), Image.Resampling.BILINEAR)
    prob_arr = np.array(prob_img) / 255.0
    pred_bin = (prob_arr >= thresh).astype(np.uint8) * 255

    # Save output binary mask
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(pred_bin).save(out_p)

    # Save visual comparison
    viz_path = out_p.with_name(out_p.stem + "_overlay.png")
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    axes[0].imshow(img1)
    axes[0].set_title("T1 (Before)")
    axes[0].axis("off")

    axes[1].imshow(img2)
    axes[1].set_title("T2 (After)")
    axes[1].axis("off")

    axes[2].imshow(prob_arr, cmap="magma")
    axes[2].set_title("Change Probability")
    axes[2].axis("off")

    # Overlay change on T2
    overlay = np.array(img2).copy()
    overlay[pred_bin == 255] = [255, 0, 0]
    axes[3].imshow(overlay)
    axes[3].set_title(f"Overlay Mask (thresh={thresh:.2f})")
    axes[3].axis("off")

    plt.tight_layout()
    plt.savefig(viz_path, dpi=120)
    plt.close()

    print(f"Binary change mask saved to: {out_p}")
    print(f"Visualization overlay saved to: {viz_path}")


def main():
    parser = argparse.ArgumentParser(description="Predict Change Mask for Bitemporal Pair")
    parser.add_argument("--t1", type=str, required=True, help="Path to T1 before image")
    parser.add_argument("--t2", type=str, required=True, help="Path to T2 after image")
    parser.add_argument("--checkpoint", type=str, required=True, help="Path to model checkpoint")
    parser.add_argument("--output", type=str, default="change_mask.png", help="Path to save change mask")
    parser.add_argument("--threshold", type=float, default=0.50, help="Change threshold")
    parser.add_argument("--size", type=int, default=256, help="Model inference size")
    args = parser.parse_args()

    predict_pair(args.t1, args.t2, args.checkpoint, args.output, image_size=args.size, threshold=args.threshold)


if __name__ == "__main__":
    main()
