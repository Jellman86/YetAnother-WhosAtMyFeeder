import pytest

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

    assert by_id["hieradet_small_inat21"].tier == "small"
    assert by_id["hieradet_small_inat21"].taxonomy_scope == "wildlife_wide"
    assert by_id["hieradet_small_inat21"].recommended_for
    assert by_id["hieradet_small_inat21"].status == "experimental"
    assert by_id["hieradet_small_inat21"].sort_order == 15
    assert by_id["hieradet_small_inat21"].download_url != "pending"
    assert by_id["hieradet_small_inat21"].labels_url != "pending"
    assert "CPU and OpenVINO CPU validated" in by_id["hieradet_small_inat21"].notes
    assert "CUDA unverified" in by_id["hieradet_small_inat21"].notes

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
