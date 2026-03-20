from pathlib import Path
import json

from scripts.export_birds_only_model import export_birds_only_model


class FakeModel:
    pretrained_cfg = {
        "mean": [0.11, 0.22, 0.33],
        "std": [0.44, 0.55, 0.66],
        "crop_pct": 0.95,
        "interpolation": "bicubic",
    }

    def eval(self):
        return self


def test_export_birds_only_model_writes_labels_and_onnx_paths(tmp_path):
    calls = {}

    def fake_loader(model_name: str):
        calls["model_name"] = model_name
        return FakeModel()

    def fake_export(model, dummy_input, output_path, **kwargs):
        calls["output_path"] = output_path
        calls["dummy_shape"] = tuple(dummy_input.shape)
        calls["kwargs"] = kwargs
        Path(output_path).write_bytes(b"fake-onnx")

    report = export_birds_only_model(
        model_name="mobilenetv4_conv_medium.e500_r224_in1k",
        output_dir=tmp_path,
        input_size=224,
        labels=["bird-a", "bird-b"],
        loader=fake_loader,
        export_fn=fake_export,
    )

    assert calls["model_name"] == "mobilenetv4_conv_medium.e500_r224_in1k"
    assert calls["dummy_shape"] == (1, 3, 224, 224)
    assert report["model_id"] == "mobilenetv4_conv_medium.e500_r224_in1k"
    assert report["model_path"] == str(tmp_path / "model.onnx")
    assert report["labels_path"] == str(tmp_path / "labels.txt")
    assert report["model_config_path"] == str(tmp_path / "model_config.json")
    assert (tmp_path / "model.onnx").read_bytes() == b"fake-onnx"
    assert (tmp_path / "labels.txt").read_text(encoding="utf-8").splitlines() == [
        "bird-a",
        "bird-b",
    ]
    config = json.loads((tmp_path / "model_config.json").read_text(encoding="utf-8"))
    assert config["runtime"] == "onnx"
    assert config["input_size"] == 224
    assert config["preprocessing"]["resize_mode"] == "center_crop"
    assert config["preprocessing"]["interpolation"] == "bicubic"
    assert config["preprocessing"]["crop_pct"] == 0.95
    assert config["preprocessing"]["mean"] == [0.11, 0.22, 0.33]
    assert config["preprocessing"]["std"] == [0.44, 0.55, 0.66]
    assert calls["kwargs"]["input_names"] == ["input"]
    assert calls["kwargs"]["output_names"] == ["output"]
    assert calls["kwargs"]["opset_version"] == 18
    assert calls["kwargs"]["dynamo"] is False


def test_export_birds_only_model_reports_external_data_sidecar(tmp_path):
    def fake_loader(model_name: str):
        return FakeModel()

    def fake_export(model, dummy_input, output_path, **kwargs):
        Path(output_path).write_bytes(b"fake-onnx")
        Path(f"{output_path}.data").write_bytes(b"fake-weights")

    report = export_birds_only_model(
        model_name="convnextv2_nano.fcmae_ft_in1k",
        output_dir=tmp_path,
        input_size=224,
        labels=["bird-a"],
        loader=fake_loader,
        export_fn=fake_export,
    )

    assert report["external_data_path"] == str(tmp_path / "model.onnx.data")
