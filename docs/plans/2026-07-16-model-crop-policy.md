# Automatic model crop policy

Date: 2026-07-18
Status: Implemented

## Decision

Image preparation is an application responsibility, not a routine owner preference. Each classifier
or regional family variant has one explicit crop policy in the model registry. The same policy is
published in the model release sidecar, while the running application remains authoritative so an
older installed sidecar cannot reverse a later evidence-based correction.

The Settings UI therefore explains the selected classifier policy under Technical details but does
not offer classifier crop mode or crop source as ordinary configuration. Crop-detector tier remains
a separate cropped-thumbnail quality choice and cannot change classifier image preparation. The few
classifiers whose validated policy requires localization use the accurate detector automatically,
with a fail-soft fallback to the fast detector. Diagnostic sweeps can still override
classifier crop behaviour in memory for the duration of a run; they do not mutate saved settings.

## Method

The Quark host evaluated the production `ClassifierService` path against one fixed panel of 144
taxonomy-verified images: three images for each of 48 common feeder species. Every model saw the same
source images with cropping forced on and off. Each family variant was selected explicitly by region.
The clean confirmation produced 4,032 classifications across all 14 installed model choices and
regional variants. It used the selected accurate YOLOX-Tiny crop detector. Crop diagnostics prove
that all 2,016 crop-on rows attempted localization: 1,736 applied a crop, 182 found no candidate above
threshold, and 98 rejected a candidate as too small. There were no detector load, inference, or model
specification failures.

Top-1 accuracy is the primary measure. A difference below two percentage points is treated as a tie,
then top-3 accuracy, Unknown rate, and median inference latency decide. This avoids enabling extra
work for noise-sized gains. The retained artifacts are:

- `/config/yawamf-eval/crop-policy-20260718-confirm2/results-standalone/summary.json`
- `/config/yawamf-eval/crop-policy-20260718-confirm2/results-na/summary.json`
- `/config/yawamf-eval/crop-policy-20260718-confirm2/results-eu/summary.json`

## Results

All accuracy values are percentages; latency is the median per image on Quark.

| Model or variant | Crop on top-1 / top-3 | Crop off top-1 / top-3 | On / off ms | Policy |
|---|---:|---:|---:|---|
| MobileNet V2 | 54.86 / 66.67 | 50.00 / 60.42 | 11.3 / 9.8 | On |
| Small Birds NA | 27.78 / 34.72 | 23.61 / 34.03 | 10.4 / 5.6 | On |
| Medium Birds NA | 33.33 / 45.14 | 31.25 / 39.58 | 102.0 / 93.4 | On |
| FlexiViT Global | 19.44 / 21.53 | 17.36 / 20.14 | 79.1 / 68.4 | On |
| Small Birds EU | 25.69 / 28.47 | 25.69 / 29.86 | 28.1 / 24.4 | Off |
| Medium Birds EU | 27.08 / 31.25 | 27.78 / 33.33 | 38.9 / 35.1 | Off |
| ConvNeXt Large | 63.19 / 71.53 | 68.75 / 76.39 | 390.5 / 355.5 | Off |
| FocalNet-B EU | 36.81 / 40.28 | 38.19 / 41.67 | 155.5 / 148.5 | Off |
| RoPE ViT-B14 | 62.50 / 71.53 | 67.36 / 75.00 | 338.8 / 305.1 | Off |
| EVA-02 Large | 68.06 / 77.78 | 67.36 / 79.86 | 734.3 / 680.7 | Off |
| MogaNet-S EU | 27.78 / 31.94 | 27.78 / 34.72 | 74.6 / 66.9 | Off |
| ConvNeXt-V1 Tiny EU | 27.78 / 32.64 | 29.17 / 35.42 | 61.6 / 54.5 | Off |
| RegNet-Y-8G EU | 25.69 / 29.86 | 26.39 / 33.33 | 77.6 / 70.4 | Off |
| UniFormer-S EU | 28.47 / 31.94 | 27.08 / 34.03 | 52.3 / 46.1 | Off |

The small EU top-1 result tied; crop-off also improved top-3, Unknown rate (9.72% versus 12.50%),
and latency. EVA-02 and UniFormer had sub-two-point top-1 differences, so their better crop-off top-3
and latency results decided the policy. The clean rerun confirmed every existing registry decision;
no model policy needed to change.

## Limits and follow-up

This is a controlled shared-panel comparison, not a claim of universal field accuracy. Public,
taxonomy-verified images are cleaner and more varied than one feeder camera, and results will change
with model or crop-detector updates. Re-run the sweep after such updates and validate against a
manually tagged feeder set once enough independent ground truth exists. Never use the active model's
own historical labels as evaluation truth.

## High-quality crop refinement follow-up

The crop-on/off policy above controls whether YA-WAMF should localise an incoming image before
classification. It is separate from high-quality snapshot candidates, which are already-localised
images generated from several clip frames. Those candidates are passed with `is_cropped=true`, so
the active model does not run a second localisation step but still applies its exact declared input
size, resize mode, interpolation, RGB conversion, normalisation, mean, and standard deviation.

The distant `birdcam` position was checked on 20 July 2026. Twelve recent events had HQ candidates;
nine selected a crop. Mean best-crop confidence was 0.762 versus 0.154 for the unchanged full-frame
candidate, a 0.598 mean gain. This field sample is not hand-labelled accuracy evidence, and one
low-confidence crop produced a conflicting label, so YA-WAMF uses it conservatively: the same
concrete species must clear the active model's recommended threshold and a 0.60 floor across at
least two distinct frames, with an 0.08 margin over any competing multi-frame consensus. Crop
sources from the same frame count once. The result may upgrade Unknown Bird or strengthen the same
known species, but cannot replace a manual tag or a conflicting known identification.
