from urllib.parse import urlparse

import pytest

from app.config import settings
from app.services.model_manager import REMOTE_REGISTRY, ModelManager


def test_every_github_release_model_asset_has_a_pinned_checksum():
    for registry_entry in REMOTE_REGISTRY:
        variants = registry_entry.get("region_variants") or {}
        model_metas = [{**registry_entry, **variant} for variant in variants.values()] if variants else [registry_entry]
        for model_meta in model_metas:
            for url_key, checksum_key in (
                ("download_url", "sha256"),
                ("weights_url", "weights_sha256"),
                ("labels_url", "labels_sha256"),
            ):
                url = str(model_meta.get(url_key) or "")
                if "/releases/download/models/" not in urlparse(url).path:
                    continue
                checksum = str(model_meta.get(checksum_key) or "")
                assert len(checksum) == 64, f"{registry_entry['id']} {url_key} is not checksum-pinned"
                assert all(character in "0123456789abcdef" for character in checksum)


def test_every_classifier_registry_entry_has_an_explicit_crop_policy():
    for model in REMOTE_REGISTRY:
        if (model.get("artifact_kind") or "classifier") != "classifier":
            continue

        variants = model.get("region_variants") or {}
        if variants:
            assert all("crop_generator" in variant for variant in variants.values()), model["id"]
        else:
            assert "crop_generator" in model, model["id"]


def test_bundled_mobilenet_registry_contract_is_pinned_and_checksum_verified():
    model = next(entry for entry in REMOTE_REGISTRY if entry["id"] == "mobilenet_v2_birds")

    assert "104342d2d3480b3e66203073dac24f4e2dbb4c41" in model["download_url"]
    assert "104342d2d3480b3e66203073dac24f4e2dbb4c41" in model["labels_url"]
    assert model["sha256"] == "350fcd8cf1df1560060d464595dfed8b174b05792788052896004848d9ad04f9"
    assert model["labels_sha256"] == "a16108dfe3f8daff015b87a97ab6a17e717b9b1bccd719f6d8f747746d7b9277"
    assert model["preprocessing"]["padding_color"] == 128


@pytest.mark.asyncio
async def test_available_models_expose_tiered_metadata():
    models = await ModelManager().list_available_models()
    by_id = {model.id: model for model in models}

    assert by_id["mobilenet_v2_birds"].tier == "cpu_only"
    assert by_id["mobilenet_v2_birds"].taxonomy_scope == "birds_only"
    assert by_id["mobilenet_v2_birds"].recommended_for
    assert by_id["mobilenet_v2_birds"].status == "stable"
    assert by_id["mobilenet_v2_birds"].sort_order == 10
    assert by_id["mobilenet_v2_birds"].model_config_url
    assert by_id["mobilenet_v2_birds"].preprocessing["resize_mode"] == "letterbox"

    assert by_id["convnext_large_inat21"].tier == "large"
    assert by_id["convnext_large_inat21"].taxonomy_scope
    assert by_id["convnext_large_inat21"].recommended_for
    assert by_id["convnext_large_inat21"].status == "stable"
    assert by_id["convnext_large_inat21"].sort_order == 20
    assert by_id["convnext_large_inat21"].model_config_url
    assert by_id["convnext_large_inat21"].preprocessing["resize_mode"] == "center_crop"
    assert by_id["convnext_large_inat21"].preprocessing["crop_pct"] == pytest.approx(0.95)
    assert by_id["convnext_large_inat21"].preprocessing["mean"] == pytest.approx([0.48145466, 0.4578275, 0.40821073])
    assert by_id["convnext_large_inat21"].preprocessing["std"] == pytest.approx([0.26862954, 0.26130258, 0.27577711])
    assert by_id["convnext_large_inat21"].supported_inference_providers == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_npu",
    ]
    assert by_id["convnext_large_inat21"].candidate_inference_providers == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]
    assert by_id["mobilenet_v2_birds"].crop_generator.enabled is True
    assert by_id["convnext_large_inat21"].crop_generator.enabled is False
    assert by_id["convnext_large_inat21"].crop_generator.input_context is None

    assert by_id["small_birds"].tier == "small"
    assert by_id["small_birds"].taxonomy_scope == "birds_only"
    assert by_id["small_birds"].region_variants
    assert {"eu", "na"} <= set(by_id["small_birds"].region_variants.keys())
    assert by_id["small_birds"].default_region == "na"
    assert by_id["small_birds"].region_variants["na"]["label_grouping"]["strategy"] == "strip_trailing_parenthetical"
    assert by_id["small_birds"].region_variants["na"]["supported_inference_providers"] == ["cpu", "intel_cpu"]
    assert by_id["small_birds"].region_variants["na"]["candidate_inference_providers"] == [
        "cpu",
        "intel_cpu",
        "intel_gpu",
    ]
    assert by_id["small_birds"].region_variants["eu"]["supported_inference_providers"] == ["cpu", "intel_cpu"]
    assert by_id["small_birds"].region_variants["eu"]["candidate_inference_providers"] == [
        "cpu",
        "intel_cpu",
        "intel_gpu",
    ]
    assert by_id["small_birds"].region_variants["eu"]["model_config_url"]
    assert by_id["small_birds"].region_variants["eu"]["preprocessing"]["resize_mode"] == "center_crop"
    assert by_id["small_birds"].region_variants["eu"]["preprocessing"]["mean"] == pytest.approx(
        [0.5248, 0.5372, 0.5086]
    )
    assert by_id["small_birds"].region_variants["eu"]["preprocessing"]["std"] == pytest.approx([0.2135, 0.2103, 0.2622])
    assert by_id["small_birds"].region_variants["na"]["model_config_url"]
    assert by_id["small_birds"].region_variants["na"]["preprocessing"]["resize_mode"] == "direct_resize"
    assert by_id["small_birds"].region_variants["na"]["crop_generator"]["enabled"] is True
    assert by_id["small_birds"].region_variants["na"]["crop_generator"]["input_context"]["is_cropped"] is True
    assert by_id["small_birds"].region_variants["eu"]["crop_generator"]["enabled"] is False

    assert by_id["medium_birds"].tier == "medium"
    assert by_id["medium_birds"].taxonomy_scope == "birds_only"
    assert by_id["medium_birds"].region_variants
    assert by_id["medium_birds"].region_variants["eu"]["region_scope"] == "eu"
    assert by_id["medium_birds"].region_variants["na"]["region_scope"] == "na"
    assert by_id["medium_birds"].region_variants["na"]["label_grouping"]["strategy"] == "strip_trailing_parenthetical"
    assert by_id["medium_birds"].region_variants["na"]["supported_inference_providers"] == ["cpu", "intel_cpu"]
    assert by_id["medium_birds"].region_variants["eu"]["supported_inference_providers"] == [
        "cpu",
        "intel_cpu",
        "intel_gpu",
    ]
    assert by_id["medium_birds"].region_variants["eu"]["candidate_inference_providers"] == [
        "cpu",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]
    assert by_id["medium_birds"].region_variants["na"]["candidate_inference_providers"] == [
        "cpu",
        "intel_cpu",
        "intel_gpu",
    ]
    assert by_id["medium_birds"].region_variants["eu"]["model_config_url"]
    assert by_id["medium_birds"].region_variants["eu"]["preprocessing"]["resize_mode"] == "center_crop"
    assert by_id["medium_birds"].region_variants["eu"]["preprocessing"]["mean"] == pytest.approx(
        [0.5191, 0.5306, 0.4877]
    )
    assert by_id["medium_birds"].region_variants["eu"]["preprocessing"]["std"] == pytest.approx(
        [0.2316, 0.2304, 0.2588]
    )
    assert by_id["medium_birds"].region_variants["na"]["model_config_url"]
    assert by_id["medium_birds"].region_variants["na"]["preprocessing"]["resize_mode"] == "direct_resize"
    assert by_id["medium_birds"].region_variants["na"]["crop_generator"]["enabled"] is True
    assert by_id["medium_birds"].region_variants["na"]["crop_generator"]["input_context"]["is_cropped"] is True
    assert by_id["medium_birds"].region_variants["eu"]["crop_generator"]["enabled"] is False

    automatic_crop_ids = {
        "mobilenet_v2_birds",
        "small_birds",
        "flexivit_il_all",
        "medium_birds",
    }
    for model_id, model in by_id.items():
        if model.artifact_kind != "classifier" or model_id in automatic_crop_ids:
            continue
        assert model.crop_generator.enabled is False, model_id

    assert by_id["rope_vit_b14_inat21"].tier == "medium"
    assert by_id["rope_vit_b14_inat21"].taxonomy_scope == "wildlife_wide"
    assert by_id["rope_vit_b14_inat21"].recommended_for
    assert by_id["rope_vit_b14_inat21"].status == "experimental"
    assert by_id["rope_vit_b14_inat21"].sort_order == 17
    assert by_id["rope_vit_b14_inat21"].download_url != "pending"
    assert by_id["rope_vit_b14_inat21"].labels_url != "pending"
    assert by_id["rope_vit_b14_inat21"].advanced_only is False
    assert "Intel CPU" in by_id["rope_vit_b14_inat21"].notes
    assert "Intel NPU" in by_id["rope_vit_b14_inat21"].notes
    assert "Intel GPU" in by_id["rope_vit_b14_inat21"].notes
    assert "host-gated" in by_id["rope_vit_b14_inat21"].notes
    assert by_id["rope_vit_b14_inat21"].supported_inference_providers == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_npu",
    ]
    assert by_id["rope_vit_b14_inat21"].candidate_inference_providers == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]
    assert by_id["rope_vit_b14_inat21"].model_config_url
    assert by_id["rope_vit_b14_inat21"].preprocessing["resize_mode"] == "center_crop"
    assert by_id["rope_vit_b14_inat21"].preprocessing["mean"] == pytest.approx([0.5248, 0.5372, 0.5086])
    assert by_id["rope_vit_b14_inat21"].preprocessing["std"] == pytest.approx([0.2135, 0.2103, 0.2622])

    assert by_id["eva02_large_inat21"].tier == "advanced"
    assert by_id["eva02_large_inat21"].taxonomy_scope
    assert by_id["eva02_large_inat21"].recommended_for
    assert by_id["eva02_large_inat21"].status == "stable"
    assert by_id["eva02_large_inat21"].sort_order == 30
    assert by_id["eva02_large_inat21"].advanced_only is True
    assert by_id["eva02_large_inat21"].model_config_url
    assert by_id["eva02_large_inat21"].preprocessing["resize_mode"] == "center_crop"
    assert by_id["eva02_large_inat21"].preprocessing["crop_pct"] == pytest.approx(1.0)
    assert by_id["eva02_large_inat21"].candidate_inference_providers == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]
    assert by_id["flexivit_il_all"].supported_inference_providers == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_npu",
    ]
    assert by_id["flexivit_il_all"].candidate_inference_providers == [
        "cpu",
        "cuda",
        "intel_cpu",
        "intel_gpu",
        "intel_npu",
    ]

    for model_id in (
        "convnext_v1_tiny_eu_common",
        "regnet_y_8g_eu_common",
        "uniformer_s_eu_common",
    ):
        assert by_id[model_id].candidate_inference_providers == [
            "cpu",
            "intel_cpu",
            "intel_gpu",
            "intel_npu",
            "cuda",
        ]

    assert by_id["bird_crop_detector"].tier == "fast"
    assert by_id["bird_crop_detector"].advanced_only is True
    assert by_id["bird_crop_detector"].runtime == "onnx"
    assert by_id["bird_crop_detector"].taxonomy_scope == "system"
    assert by_id["bird_crop_detector"].model_config_url
    assert by_id["bird_crop_detector"].notes
    assert by_id["bird_crop_detector"].input_size == 300
    assert by_id["bird_crop_detector"].preprocessing["resize_mode"] == "direct_resize"
    assert by_id["bird_crop_detector_accurate_yolox_tiny"].supported_inference_providers == [
        "cpu",
        "intel_cpu",
        "cuda",
        "intel_gpu",
        "intel_npu",
    ]


@pytest.mark.asyncio
async def test_available_models_disable_invalid_crop_generator_metadata(monkeypatch):
    from app.services import model_manager as model_manager_module

    monkeypatch.setattr(
        model_manager_module,
        "REMOTE_REGISTRY",
        [
            dict(
                model_manager_module.REMOTE_REGISTRY[0],
                crop_generator={"enabled": "not-a-bool", "input_context": {"is_cropped": "also-bad"}},
            )
        ],
    )

    models = await ModelManager().list_available_models()

    assert models[0].crop_generator.enabled is False
    assert models[0].crop_generator.input_context is None


@pytest.mark.asyncio
async def test_available_models_resolve_family_variant_sizes_from_settings():
    manager = ModelManager()

    original_country = settings.location.country
    original_override = settings.classification.bird_model_region_override
    try:
        settings.location.country = "GB"
        settings.classification.bird_model_region_override = "auto"
        eu_models = await manager.list_available_models()
        eu_by_id = {model.id: model for model in eu_models}

        assert eu_by_id["small_birds"].file_size_mb == pytest.approx(122.7, abs=0.1)
        assert eu_by_id["medium_birds"].file_size_mb == pytest.approx(108.5, abs=0.1)
        assert "intel_cpu" in (eu_by_id["small_birds"].supported_inference_providers or [])
        assert "intel_cpu" in (eu_by_id["medium_birds"].supported_inference_providers or [])
        assert eu_by_id["small_birds"].candidate_inference_providers == ["cpu", "intel_cpu", "intel_gpu"]
        assert eu_by_id["medium_birds"].candidate_inference_providers == [
            "cpu",
            "intel_cpu",
            "intel_gpu",
            "intel_npu",
        ]

        settings.location.country = "US"
        settings.classification.bird_model_region_override = "auto"
        na_models = await manager.list_available_models()
        na_by_id = {model.id: model for model in na_models}

        assert na_by_id["small_birds"].file_size_mb == pytest.approx(18.0, abs=0.1)
        assert na_by_id["medium_birds"].file_size_mb == pytest.approx(333.0, abs=0.1)
        assert na_by_id["small_birds"].supported_inference_providers == ["cpu", "intel_cpu"]
        assert na_by_id["small_birds"].candidate_inference_providers == ["cpu", "intel_cpu", "intel_gpu"]
        assert na_by_id["medium_birds"].supported_inference_providers == ["cpu", "intel_cpu"]
        assert na_by_id["medium_birds"].candidate_inference_providers == ["cpu", "intel_cpu", "intel_gpu"]
    finally:
        settings.location.country = original_country
        settings.classification.bird_model_region_override = original_override


@pytest.mark.asyncio
async def test_available_models_ignore_legacy_crop_overrides_from_settings():
    manager = ModelManager()

    original_country = settings.location.country
    original_override = settings.classification.bird_model_region_override
    original_crop_model_overrides = settings.classification.crop_model_overrides
    original_crop_source_overrides = settings.classification.crop_source_overrides
    try:
        settings.location.country = "US"
        settings.classification.bird_model_region_override = "auto"
        settings.classification.crop_model_overrides = {"small_birds.na": "off"}
        settings.classification.crop_source_overrides = {"small_birds.na": "standard"}

        models = await manager.list_available_models()
        by_id = {model.id: model for model in models}

        assert by_id["small_birds"].crop_generator.enabled is True
        assert by_id["small_birds"].crop_generator.source_preference == "high_quality"
    finally:
        settings.location.country = original_country
        settings.classification.bird_model_region_override = original_override
        settings.classification.crop_model_overrides = original_crop_model_overrides
        settings.classification.crop_source_overrides = original_crop_source_overrides
