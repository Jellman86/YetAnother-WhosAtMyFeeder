- YA-WAMF's images now run on Python 3.13 instead of 3.12. Nothing changes in how it
  identifies birds: on the same photos the 3.12 and 3.13 images gave identical species and
  scores on CPU, an Intel GPU and an Intel NPU, with the same versions of TensorFlow, ONNX
  Runtime and OpenVINO. Python 3.15 was proposed and is not possible yet, because those
  runtimes publish no builds for it; 3.14 would have installed a pre-release TensorFlow. The
  evidence is in
  [the readiness review](docs/reviews/2026-11-13-python-upgrade-readiness.md). The CUDA image
  was built and starts, but could not be tried on an NVIDIA GPU. If you develop YA-WAMF,
  recreate your virtual environment with Python 3.13.
