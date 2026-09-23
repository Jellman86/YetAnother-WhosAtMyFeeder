"""Real installed-model gates; each native inference lives in a disposable child."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.run_model_hardware_gate import BACKEND, PROVIDERS


@pytest.mark.parametrize("provider", PROVIDERS)
def test_installed_models_pass_the_isolated_provider_gate(provider: str, tmp_path: Path) -> None:
    root = Path(os.environ.get("YAWAMF_TEST_MODEL_DIR", "/data/models"))
    if not root.is_dir() or not any(root.rglob("model_config.json")):
        pytest.skip("No installed model library; use the hardware runner on a trusted test host")
    if provider.startswith("intel_"):
        if importlib.util.find_spec("openvino") is None:
            pytest.skip("OpenVINO is not installed")
        import openvino

        if provider.removeprefix("intel_").upper() not in openvino.Core().available_devices:
            pytest.skip(f"No {provider} device on this host")
    elif provider == "cuda":
        if importlib.util.find_spec("onnxruntime") is None:
            pytest.skip("ONNX Runtime is not installed")
        import onnxruntime

        if "CUDAExecutionProvider" not in onnxruntime.get_available_providers():
            pytest.skip("CUDA runtime not packaged on this host")
    result = subprocess.run(
        [
            sys.executable,
            str(BACKEND / "scripts/run_model_hardware_gate.py"),
            "--models-dir",
            str(root),
            "--output",
            str(tmp_path / "hardware-results"),
            "--provider",
            provider,
        ],
        check=False,
    )
    assert result.returncode == 0, (
        f"{provider} hardware gate failed; inspect {tmp_path / 'hardware-results/summary.json'}"
    )
