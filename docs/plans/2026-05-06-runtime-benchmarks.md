# Runtime Benchmarks Diagnostics

## Goal

Complete Issue #33 Phase 4 by adding a startup runtime benchmark that compares accelerated ONNX candidates against a comparable CPU baseline before the accelerated runtime is mounted.

## Behavior

- Run for accelerated ONNX candidates during in-process startup:
  - `openvino/intel_gpu` compared with `openvino/intel_cpu`.
  - `onnxruntime/cuda` compared with `onnxruntime/cpu`.
- Use the existing synthetic startup self-test image so the benchmark is deterministic and independent of live camera state.
- Refuse the accelerated candidate when single-frame latency is greater than `CLASSIFIER_RUNTIME_BENCHMARK_MAX_GPU_CPU_RATIO` times the comparable CPU baseline.
- Default the max ratio to `5.0`.
- If the benchmark cannot run or CPU baseline is unavailable, record diagnostics and continue instead of blocking startup.
- Expose the last diagnostics through classifier status and health as `runtime_benchmarks`.

## Verification

- Focused classifier service tests for OpenVINO GPU refusal/acceptance, ONNX Runtime CUDA refusal/acceptance, and health/status diagnostics.
- Focused startup self-test tests for existing OpenVINO diagnostics.
