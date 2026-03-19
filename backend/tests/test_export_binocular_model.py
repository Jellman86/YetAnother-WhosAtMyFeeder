from pathlib import Path

from scripts.export_binocular_model import export_binocular_model, load_binocular_model


class FakeEncoder:
    def __call__(self, x):
        return x


class FakeModel:
    def __init__(self):
        self.loaded_state = None
        self.eval_called = False

    def load_state_dict(self, state):
        self.loaded_state = state

    def eval(self):
        self.eval_called = True
        return self


def test_load_binocular_model_builds_model_from_checkpoint_metadata(tmp_path):
    checkpoint_path = tmp_path / "binocular.pth"
    checkpoint = {
        "config": {"encoder_name": "dinov2_vitb14"},
        "class_names": ["Blue Jay", "Cardinalis cardinalis"],
        "model_state_dict": {"classifier.classifier.0.weight": [[1.0]], "classifier.classifier.0.bias": [0.0]},
    }
    checkpoint_path.write_bytes(b"placeholder")

    calls = {}
    fake_model = FakeModel()

    def fake_checkpoint_loader(*, repo_id: str, filename: str):
        calls["repo_id"] = repo_id
        calls["filename"] = filename
        return str(checkpoint_path)

    def fake_torch_load(path: str, map_location: str = "cpu", weights_only: bool = False):
        calls["torch_load"] = {
            "path": path,
            "map_location": map_location,
            "weights_only": weights_only,
        }
        return checkpoint

    def fake_model_builder(*, encoder_name: str, num_classes: int, encoder_loader=None):
        calls["model_builder"] = {
            "encoder_name": encoder_name,
            "num_classes": num_classes,
            "encoder_loader": encoder_loader,
        }
        return fake_model

    model, labels, config = load_binocular_model(
        repo_id="jiujiuche/binocular",
        filename="artifacts/dinov2_vitb14_nabirds.pth",
        checkpoint_loader=fake_checkpoint_loader,
        torch_load=fake_torch_load,
        model_builder=fake_model_builder,
        encoder_loader=lambda repo, model: FakeEncoder(),
    )

    assert model is fake_model
    assert labels == ["Blue Jay", "Cardinalis cardinalis"]
    assert config == {"encoder_name": "dinov2_vitb14"}
    assert fake_model.loaded_state == checkpoint["model_state_dict"]
    assert calls["repo_id"] == "jiujiuche/binocular"
    assert calls["filename"] == "artifacts/dinov2_vitb14_nabirds.pth"
    assert calls["torch_load"]["path"] == str(checkpoint_path)
    assert calls["torch_load"]["map_location"] == "cpu"
    assert calls["torch_load"]["weights_only"] is False
    assert calls["model_builder"] == {
        "encoder_name": "dinov2_vitb14",
        "num_classes": 2,
        "encoder_loader": calls["model_builder"]["encoder_loader"],
    }


def test_export_binocular_model_writes_labels_and_onnx_paths(tmp_path):
    calls = {}
    fake_model = FakeModel()

    def fake_loader(*, repo_id, filename, checkpoint_loader=None, torch_load=None, model_builder=None, encoder_loader=None):
        calls["repo_id"] = repo_id
        calls["filename"] = filename
        return fake_model, ["Blue Jay", "Northern Cardinal"], {"image_size": 224}

    def fake_export(model, dummy_input, output_path, **kwargs):
        calls["dummy_shape"] = tuple(dummy_input.shape)
        calls["output_path"] = output_path
        calls["kwargs"] = kwargs
        Path(output_path).write_bytes(b"fake-onnx")

    report = export_binocular_model(
        output_dir=tmp_path,
        loader=fake_loader,
        export_fn=fake_export,
    )

    assert calls["repo_id"] == "jiujiuche/binocular"
    assert calls["filename"] == "artifacts/dinov2_vitb14_nabirds.pth"
    assert calls["dummy_shape"] == (1, 3, 224, 224)
    assert fake_model.eval_called is True
    assert report["model_id"] == "jiujiuche/binocular"
    assert report["model_path"] == str(tmp_path / "model.onnx")
    assert report["labels_path"] == str(tmp_path / "labels.txt")
    assert (tmp_path / "labels.txt").read_text(encoding="utf-8").splitlines() == [
        "Blue Jay",
        "Northern Cardinal",
    ]
    assert calls["kwargs"]["input_names"] == ["input"]
    assert calls["kwargs"]["output_names"] == ["output"]
    assert calls["kwargs"]["opset_version"] == 18
    assert calls["kwargs"]["dynamo"] is True
