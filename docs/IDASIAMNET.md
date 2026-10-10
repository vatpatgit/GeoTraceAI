# IDA-SiamNet change detection (LEVIR-CD)

Reimplementation, in plain PyTorch, of the architecture in https://github.com/SUPERMAN123000/IDA-SiamNet (Open-CD / mmcv based):

* **Interactive backbone** - one weight-shared ResNet for both dates; after stages 2-4 the two feature maps exchange information through
  `SEFI` (spatial attention using the other date's max map) and `CEFI` (channel attention using the other date's depthwise-separable features).
* **Dynamic-aware head** - per-date multi-scale features are projected, upsampled and fused; `FDAF` aligns the dates with an adaptive
  (deformable + gated) convolution and a learned flow warp, takes cross-date differences, and a MixFFN produces the change logit.

Code: `ML/terratrack/models/idasiamnet.py` (model), `ML/scripts/train_idasiamnet_levir.py` (training / evaluation),
`backend/app/ml/` (`arch: idasiamnet` registry entries are loaded by the backend detector).

Differences from the reference, stated plainly: ResNet50 with ImageNet weights from the local torch cache (ResNet18 / MiT-b1 weights are not
available offline); BatchNorm instead of SyncBN; one sigmoid logit with BCE + Dice instead of 2-class softmax with OHEM; 256 px training crops
(batch 8, 12,000 iterations, AdamW, poly schedule) instead of 512 px / 40k iterations because of the 4 GB GPU.

## Results (LEVIR-CD, whole 1024 x 1024 images at native 0.5 m, pixel-level change class)

| Model | Split | F1 | IoU | Precision | Recall |
|---|---|---|---|---|---|
| IDA-SiamNet (this work) | val (64 pairs, used for checkpoint + threshold) | 0.911 | 0.837 | 0.916 | 0.907 |
| IDA-SiamNet (this work) | **test (128 pairs, scored once)** | **0.913** | **0.840** | 0.923 | 0.903 |
| previous `levir-cd-v1` (Siamese ResNet50-UNet) | test, its own protocol (images resized to 256 px) | 0.726 | 0.570 | 0.707 | 0.746 |

Through the running app (`POST /imagery/plain-ml-changes`, polygons rasterised and compared to the labels) on 8 held-out test pairs:
IDA-SiamNet F1 0.901 vs 0.340 for `levir-cd-v1`; the older model was being fed 0.5 m aerial images at a scale it was not trained for.

## In the app

Registered as `idasiamnet-levir-v1` (0.5 m, threshold 0.75). Uploaded / plain aerial images (finer than 5 m per pixel) now use it automatically
(`app/services/upload_compare.py`), falling back to `levir-cd-v1` if it is not installed. Sentinel-2 comparisons still use `oscd-s2-v1`.

## Limits

* Trained on 0.5 m RGB aerial imagery of US cities for building change; **not validated on Sentinel-2 / 10 m imagery**, other regions or change types.
* LEVIR-CD test images come from the same cities as training images; expect lower scores on new places.
* Reproduce: `python ML/scripts/train_idasiamnet_levir.py --iters 12000` (about 55 minutes on an RTX 3050 Laptop).
