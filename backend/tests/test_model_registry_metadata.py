import pytest

from app.config import settings
from app.services.model_manager import ModelManager


@pytest.mark.asyncio
async def test_available_models_expose_tiered_metadata():
    models = await ModelManager().list_available_models()
    by_id = {model.id: model for model in models}

    assert by_id["mobilenet_v2_birds"].tier == "cpu_only"
    assert by_id["mobilenet_v2_birds"].taxonomy_scope == "birds_only"
    assert by_id["mobilenet_v2_birds"].recommended_for
    assert by_id["mobilenet_v2_birds"].status == "stable"
    assert by_id["mobilenet_v2_birds"].sort_order == 10

    assert by_id["convnext_large_inat21"].tier == "large"
    assert by_id["convnext_large_inat21"].taxonomy_scope
    assert by_id["convnext_large_inat21"].recommended_for
    assert by_id["convnext_large_inat21"].status == "stable"
    assert by_id["convnext_large_inat21"].sort_order == 20

    assert by_id["small_birds"].tier == "small"
    assert by_id["small_birds"].taxonomy_scope == "birds_only"
    assert by_id["small_birds"].region_variants
    assert {"eu", "na"} <= set(by_id["small_birds"].region_variants.keys())
    assert by_id["small_birds"].default_region == "na"
    assert by_id["small_birds"].region_variants["na"]["label_grouping"]["strategy"] == "strip_trailing_parenthetical"
    assert by_id["small_birds"].region_variants["na"]["supported_inference_providers"] == ["cpu", "intel_cpu"]

    assert by_id["medium_birds"].tier == "medium"
    assert by_id["medium_birds"].taxonomy_scope == "birds_only"
    assert by_id["medium_birds"].region_variants
    assert by_id["medium_birds"].region_variants["eu"]["region_scope"] == "eu"
    assert by_id["medium_birds"].region_variants["na"]["region_scope"] == "na"
    assert by_id["medium_birds"].region_variants["na"]["label_grouping"]["strategy"] == "strip_trailing_parenthetical"
    assert by_id["medium_birds"].region_variants["na"]["supported_inference_providers"] == ["cpu", "intel_cpu"]

    assert by_id["hieradet_small_inat21"].tier == "small"
    assert by_id["hieradet_small_inat21"].taxonomy_scope == "wildlife_wide"
    assert by_id["hieradet_small_inat21"].recommended_for
    assert by_id["hieradet_small_inat21"].status == "experimental"
    assert by_id["hieradet_small_inat21"].sort_order == 15
    assert by_id["hieradet_small_inat21"].name == "ViT Small (Balanced)"
    assert by_id["hieradet_small_inat21"].architecture == "ViT Reg4 M16 RMS Avg (I-JEPA)"
    assert by_id["hieradet_small_inat21"].download_url != "pending"
    assert by_id["hieradet_small_inat21"].weights_url != "pending"
    assert by_id["hieradet_small_inat21"].labels_url != "pending"
    assert "Intel GPU validated" in by_id["hieradet_small_inat21"].notes
    assert "CUDA unverified and best-effort only" in by_id["hieradet_small_inat21"].notes

    assert by_id["rope_vit_b14_inat21"].tier == "medium"
    assert by_id["rope_vit_b14_inat21"].taxonomy_scope == "wildlife_wide"
    assert by_id["rope_vit_b14_inat21"].recommended_for
    assert by_id["rope_vit_b14_inat21"].status == "experimental"
    assert by_id["rope_vit_b14_inat21"].sort_order == 18
    assert by_id["rope_vit_b14_inat21"].download_url != "pending"
    assert by_id["rope_vit_b14_inat21"].labels_url != "pending"
    assert by_id["rope_vit_b14_inat21"].advanced_only is False
    assert "CPU and OpenVINO CPU validated" in by_id["rope_vit_b14_inat21"].notes
    assert "CUDA unverified" in by_id["rope_vit_b14_inat21"].notes

    assert by_id["eva02_large_inat21"].tier == "advanced"
    assert by_id["eva02_large_inat21"].taxonomy_scope
    assert by_id["eva02_large_inat21"].recommended_for
    assert by_id["eva02_large_inat21"].status == "stable"
    assert by_id["eva02_large_inat21"].sort_order == 30
    assert by_id["eva02_large_inat21"].advanced_only is True


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
        assert "intel_gpu" in (eu_by_id["small_birds"].supported_inference_providers or [])
        assert "intel_gpu" in (eu_by_id["medium_birds"].supported_inference_providers or [])

        settings.location.country = "US"
        settings.classification.bird_model_region_override = "auto"
        na_models = await manager.list_available_models()
        na_by_id = {model.id: model for model in na_models}

        assert na_by_id["small_birds"].file_size_mb == pytest.approx(18.0, abs=0.1)
        assert na_by_id["medium_birds"].file_size_mb == pytest.approx(333.0, abs=0.1)
        assert na_by_id["small_birds"].supported_inference_providers == ["cpu", "intel_cpu"]
        assert na_by_id["medium_birds"].supported_inference_providers == ["cpu", "intel_cpu"]
    finally:
        settings.location.country = original_country
        settings.classification.bird_model_region_override = original_override
