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

    assert by_id["eva02_large_inat21"].tier == "advanced"
    assert by_id["eva02_large_inat21"].taxonomy_scope
    assert by_id["eva02_large_inat21"].recommended_for
    assert by_id["eva02_large_inat21"].status == "stable"
    assert by_id["eva02_large_inat21"].sort_order == 30
    assert by_id["eva02_large_inat21"].advanced_only is True
