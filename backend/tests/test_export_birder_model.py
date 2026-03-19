from pathlib import Path

from scripts.export_birder_model import export_birder_model


class FakeModel:
    def eval(self):
        return self


def test_export_birder_model_writes_labels_and_onnx_paths(tmp_path):
    calls = {}

    def fake_loader(model_id: str, *, cache_dir=None):
        calls["model_id"] = model_id
        calls["cache_dir"] = cache_dir
        return FakeModel(), ["anser_caerulescens", "cyanocitta_cristata"]

    def fake_export(model, dummy_input, output_path, **kwargs):
        calls["output_path"] = output_path
        calls["dummy_shape"] = tuple(dummy_input.shape)
        calls["kwargs"] = kwargs
        Path(output_path).write_bytes(b"fake-onnx")

    report = export_birder_model(
        model_id="birder-project/hieradet_d_small_dino-v2-inat21-256px",
        output_dir=tmp_path,
        input_size=256,
        loader=fake_loader,
        export_fn=fake_export,
    )

    assert calls["model_id"] == "hieradet_d_small_dino-v2-inat21-256px"
    assert calls["cache_dir"] == tmp_path.parent / ".birder-cache"
    assert calls["dummy_shape"] == (1, 3, 256, 256)
    assert report["model_path"] == str(tmp_path / "model.onnx")
    assert report["labels_path"] == str(tmp_path / "labels.txt")
    assert (tmp_path / "model.onnx").read_bytes() == b"fake-onnx"
    assert (tmp_path / "labels.txt").read_text(encoding="utf-8").splitlines() == [
        "anser_caerulescens",
        "cyanocitta_cristata",
    ]
    assert calls["kwargs"]["input_names"] == ["input"]
    assert calls["kwargs"]["output_names"] == ["output"]
    assert calls["kwargs"]["opset_version"] == 18
    assert calls["kwargs"]["dynamo"] is False
    assert calls["cache_dir"] == tmp_path.parent / ".birder-cache"


def test_export_birder_model_normalizes_birder_repo_prefix(tmp_path):
    calls = {}

    def fake_loader(model_id: str, *, cache_dir=None):
        calls["model_id"] = model_id
        calls["cache_dir"] = cache_dir
        return FakeModel(), ["label"]

    def fake_export(model, dummy_input, output_path, **kwargs):
        Path(output_path).write_bytes(b"fake-onnx")

    export_birder_model(
        model_id="birder-project/hieradet_d_small_dino-v2-inat21-256px",
        output_dir=tmp_path,
        input_size=256,
        loader=fake_loader,
        export_fn=fake_export,
    )

    assert calls["model_id"] == "hieradet_d_small_dino-v2-inat21-256px"
