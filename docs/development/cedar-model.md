# Cedar motion detector artifact

The optional motion collector uses MegaDetector v1000.0.0 Cedar, converted to a
static raw-head ONNX graph. Its catalogue package is
[`garden_md1000_cedar.json`](../../backend/app/assets/garden_md1000_cedar.json).
This is a generic animal/person/vehicle detector, not a species classifier or a
replacement for Frigate's bird detector.

The [models release](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/tag/models)
distributes `md1000-cedar.onnx`, its catalogue metadata, checksum list and a source
bundle. The graph is 101,228,666 bytes, SHA-256
`1a1f32bf00b10ed4907dca7d05c66fef8ac37adc48526cdfdf957eaa0e2ffff3`.

## Source and licence

- Original checkpoint: [MegaDetector v1000 release](https://github.com/agentmorris/MegaDetector/releases/tag/v1000.0),
  `md_v1000.0.0-cedar.pt`, SHA-256
  `48f72a8b086dfd6a3ef6defaef422bd4a250b9084981044dcc2bb35764c93ca5`.
- Architecture: [WongKinYiu/yolov9](https://github.com/WongKinYiu/yolov9/tree/5b1ea9a8b3f0ffe4fe0e203ec6232d788bb3fcff),
  revision `5b1ea9a8b3f0ffe4fe0e203ec6232d788bb3fcff`, GPL-3.0.
- [MegaDetector's licence statement](https://huggingface.co/agentmorris/megadetector/blob/main/LICENSE)
  describes its related code as MIT and says the proprietary training-data licence
  places no restrictions on model use. The training data is not redistributed.
  The separate source bundle includes the architecture's GPL text and complete
  pinned source alongside the conversion recipe. Catalogue metadata is MIT.

## Conversion and qualification

In a disposable environment, install upstream requirements with CPU PyTorch,
ONNX and ONNX Runtime. The original conversion used PyTorch 2.14.1, ONNX 1.23.2,
ONNX Runtime 1.31.0, NumPy 2.5.4 and OpenCV 5.0.0. Pin the architecture revision
above. Use an external process deadline and memory guard; run one native job at
a time. The checkpoint's Python objects are unpickled only after its trusted
checksum matches.

```bash
python backend/scripts/export_garden_cedar.py \
  --source /private/yolov9 --checkpoint /private/md_v1000.0.0-cedar.pt \
  --output /private/md1000-cedar.onnx
```

The script checks the raw `1×7×8400` output and CPU agreement against the original
checkpoint. Fresh exports can have different bytes with different exporter versions;
the application accepts only the distributed checksum. Qualification also compared
five public-image outputs against the checkpoint: maximum coordinate error below
0.004 pixels and score error below 0.00004. This establishes conversion agreement,
not detection accuracy or local mammal recall.

Runtime input is uint8 BGR decoded by OpenCV, converted to RGB, letterboxed to 640
with fill 114, then contiguous float32 NCHW divided by 255. Raw class probabilities
use independent class NMS at IoU 0.45, with animal/person/vehicle thresholds
0.5/0.2/0.4. A person in any sampled frame rejects the whole recording. Person
checks operate independently of the highest-scoring class. Boxes are unpadded to
normalized XYWH in the sampled full frame before its bounded JPEG is retained.
Every retained proposal binds the clip, RGB frame, input tensor, JPEG and model
checksums. These thresholds are conservative prototype choices, not calibrated
local accuracy metrics. Real reviewed daytime and infrared mammals remain needed.
