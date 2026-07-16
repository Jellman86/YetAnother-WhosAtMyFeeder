# Automatic model crop policy

Date: 2026-07-16
Status: Implemented

## Decision

Image preparation is an application responsibility, not a routine owner preference. Each classifier
or regional family variant has one explicit crop policy in the model registry. The same policy is
published in the model release sidecar, while the running application remains authoritative so an
older installed sidecar cannot reverse a later evidence-based correction.

The Settings UI therefore explains the selected policy under Technical details but does not offer
crop mode, crop source, or crop-detector tier as ordinary configuration. Diagnostic sweeps can still
override crop behaviour in memory for the duration of a run; they do not mutate saved settings.

## Method

The Quark host evaluated the production `ClassifierService` path against one fixed panel of 144
taxonomy-verified images: three images for each of 48 common feeder species. Every model saw the same
source images with cropping forced on and off. Each family variant was selected explicitly by region.
The confirmation run produced 3,456 classifications for the 12 installed model choices; the EU
variant follow-up added 576 classifications.

Top-1 accuracy is the primary measure. A difference below two percentage points is treated as a tie,
then top-3 accuracy, Unknown rate, and median inference latency decide. This avoids enabling extra
work for noise-sized gains. The retained artifacts are:

- `/config/yawamf-eval/crop-policy-20260716-confirm/results/summary.json`
- `/config/yawamf-eval/crop-policy-20260716-eu/results/summary.json`

## Results

All accuracy values are percentages; latency is the median per image on Quark.

| Model or variant | Crop on top-1 / top-3 | Crop off top-1 / top-3 | On / off ms | Policy |
|---|---:|---:|---:|---|
| MobileNet V2 | 54.86 / 66.67 | 50.00 / 60.42 | 11.1 / 10.1 | On |
| Small Birds NA | 27.78 / 34.72 | 23.61 / 34.03 | 9.2 / 5.9 | On |
| Medium Birds NA | 33.33 / 45.14 | 31.25 / 39.58 | 100.7 / 93.6 | On |
| FlexiViT Global | 19.44 / 21.53 | 17.36 / 20.14 | 78.6 / 68.0 | On |
| Small Birds EU | 25.69 / 28.47 | 25.69 / 29.86 | 27.5 / 24.4 | Off |
| Medium Birds EU | 27.08 / 31.25 | 27.78 / 33.33 | 44.8 / 33.5 | Off |
| ConvNeXt Large | 63.19 / 71.53 | 68.75 / 76.39 | 389.6 / 355.1 | Off |
| FocalNet-B EU | 36.81 / 40.28 | 38.19 / 41.67 | 154.9 / 150.9 | Off |
| RoPE ViT-B14 | 62.50 / 71.53 | 67.36 / 75.00 | 334.8 / 304.2 | Off |
| EVA-02 Large | 68.06 / 77.78 | 67.36 / 79.86 | 727.3 / 680.2 | Off |
| MogaNet-S EU | 27.78 / 31.94 | 27.78 / 34.72 | 79.2 / 67.0 | Off |
| ConvNeXt-V1 Tiny EU | 27.78 / 32.64 | 29.17 / 35.42 | 69.9 / 54.2 | Off |
| RegNet-Y-8G EU | 25.69 / 29.86 | 26.39 / 33.33 | 84.6 / 69.6 | Off |
| UniFormer-S EU | 28.47 / 31.94 | 27.08 / 34.03 | 62.4 / 45.9 | Off |

The small EU top-1 result tied; crop-off also improved top-3, Unknown rate (9.72% versus 12.50%),
and latency. EVA-02 and UniFormer had sub-two-point top-1 differences, so their better crop-off top-3
and latency results decided the policy.

## Limits and follow-up

This is a controlled shared-panel comparison, not a claim of universal field accuracy. Public,
taxonomy-verified images are cleaner and more varied than one feeder camera, and results will change
with model or crop-detector updates. Re-run the sweep after such updates and validate against a
manually tagged feeder set once enough independent ground truth exists. Never use the active model's
own historical labels as evaluation truth.
