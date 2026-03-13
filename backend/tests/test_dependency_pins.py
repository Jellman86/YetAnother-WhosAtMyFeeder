from pathlib import Path


def _load_requirements() -> str:
    requirements = Path(__file__).resolve().parents[1] / "requirements.txt"
    return requirements.read_text(encoding="utf-8")


def test_openvino_is_pinned_to_known_good_series():
    content = _load_requirements()
    openvino_lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith("openvino")
    ]
    assert openvino_lines, "openvino requirement missing"
    assert openvino_lines[0] == "openvino==2024.6.0"
