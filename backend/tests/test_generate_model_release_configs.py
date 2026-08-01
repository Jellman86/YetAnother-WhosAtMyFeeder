import json
from pathlib import Path

from scripts.generate_model_release_configs import build_release_model_configs


ASSETS_DIR = Path(__file__).resolve().parents[1] / "app" / "assets"


def test_release_model_configs_cover_every_registry_sidecar_once():
    configs = build_release_model_configs()

    assert len(configs) == 12
    assert len(configs) == len(set(configs))
    assert "rope_vit_b14_inat21_model_config.json" in configs
    assert "small_birds_eu_mobilenet_v4_l_candidate_model_config.json" in configs
    assert "small_birds_na_efficientnet_b0_candidate_model_config.json" in configs
    assert "moganet_s_eu_common_model_config.json" not in configs
    assert "convnext_v1_tiny_eu_common_model_config.json" not in configs
    assert "regnet_y_8g_eu_common_model_config.json" not in configs
    assert "uniformer_s_eu_common_model_config.json" not in configs


def test_release_model_configs_use_current_provider_policy():
    configs = build_release_model_configs()

    assert configs["convnext_large_inat21_model_config.json"]["supported_inference_providers"] == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_npu",
    ]
    assert configs["convnext_large_inat21_model_config.json"]["candidate_inference_providers"] == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]
    assert configs["rope_vit_b14_inat21_model_config.json"]["supported_inference_providers"] == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_npu",
    ]
    assert configs["rope_vit_b14_inat21_model_config.json"]["candidate_inference_providers"] == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]
    assert configs["flexivit_il_all_model_config.json"]["supported_inference_providers"] == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_npu",
    ]
    assert configs["flexivit_il_all_model_config.json"]["candidate_inference_providers"] == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]
    assert configs["eu_medium_focalnet_b_model_config.json"]["supported_inference_providers"] == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]
    assert configs["medium_birds_eu_convnext_v2_tiny_256_candidate_model_config.json"][
        "candidate_inference_providers"
    ] == [
        "cpu",
        "intel_cpu",
        "intel_gpu",
    ]
    assert configs["medium_birds_na_binocular_candidate_model_config.json"]["candidate_inference_providers"] == [
        "cpu",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]
    assert configs["eva02_large_inat21_model_config.json"]["candidate_inference_providers"] == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]
    assert configs["bird_crop_detector_accurate_yolox_tiny_model_config.json"]["supported_inference_providers"] == [
        "cpu",
        "intel_cpu",
        "cuda",
        "intel_gpu",
        "intel_npu",
    ]
    assert configs["small_birds_eu_mobilenet_v4_l_candidate_model_config.json"]["supported_inference_providers"] == [
        "cpu",
        "intel_cpu",
    ]
    assert configs["small_birds_eu_mobilenet_v4_l_candidate_model_config.json"]["candidate_inference_providers"] == [
        "cpu",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]
    assert configs["small_birds_eu_mobilenet_v4_l_candidate_model_config.json"] == {
        **configs["small_birds_eu_mobilenet_v4_l_candidate_model_config.json"],
        "model_id": "small_birds",
        "region_scope": "eu",
    }


def test_release_model_configs_keep_classifier_crop_policy_separate_from_detector_metadata():
    configs = build_release_model_configs()

    assert configs["mobilenet_v2_birds_model_config.json"]["crop_generator"] == {
        "enabled": True,
        "source_preference": "standard",
    }
    assert configs["convnext_large_inat21_model_config.json"]["crop_generator"] == {
        "enabled": False,
        "source_preference": "standard",
    }
    assert configs["small_birds_na_efficientnet_b0_candidate_model_config.json"]["crop_generator"] == {
        "enabled": True,
        "source_preference": "high_quality",
        "input_context": {"is_cropped": True},
    }
    assert configs["small_birds_eu_mobilenet_v4_l_candidate_model_config.json"]["crop_generator"] == {
        "enabled": False,
        "source_preference": "standard",
    }
    assert configs["bird_crop_detector_accurate_yolox_tiny_model_config.json"]["artifact_kind"] == "crop_detector"
    assert "crop_generator" not in configs["bird_crop_detector_accurate_yolox_tiny_model_config.json"]


def test_release_model_configs_include_runtime_preprocessing_and_checksums():
    configs = build_release_model_configs()
    convnext = configs["convnext_large_inat21_model_config.json"]

    assert convnext["runtime"] == "onnx"
    assert convnext["input_size"] == 384
    assert convnext["preprocessing"]["resize_mode"] == "center_crop"
    assert convnext["sha256"] == "4717dd31182c8bbcd1058f7dee1c6099feb604a44d6576315386c4d6d9f781f6"
    assert convnext["weights_sha256"] == "b6157639e013433bb28deae7da5653144822dcaeebfec14fa743c86cd91907c2"
    assert convnext["labels_sha256"] == "f2b1294bc0b3a943425655e8b74cd7489e623d0ec7fa6dc5ce57cc85a93f8ac5"


def test_bundled_sidecar_is_generated_from_the_canonical_registry():
    bundled = json.loads((ASSETS_DIR / "model_config.json").read_text(encoding="utf-8"))

    assert bundled == build_release_model_configs()["mobilenet_v2_birds_model_config.json"]
