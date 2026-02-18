from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.services.ebird_service import EbirdService, _normalize_name


def test_normalize_name_is_unicode_safe():
    assert _normalize_name("Černý kos") == _normalize_name("cerny kos")
    assert _normalize_name("Чёрный дрозд") != ""
    assert _normalize_name("   ") == ""


@pytest.mark.asyncio
async def test_resolve_species_code_rejects_empty_normalized_lookup(monkeypatch):
    service = EbirdService()
    service._taxonomy_cache = {
        "en": {
            "fetched_at": datetime.now(timezone.utc),
            "items": [],
            "index": {"": "bad-code", "robin": "amerob"},
        }
    }
    monkeypatch.setattr(service, "get_taxonomy", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "resolve_locale", AsyncMock(return_value="en"))

    code = await service.resolve_species_code("!!!", locale="en")
    assert code is None


@pytest.mark.asyncio
async def test_resolve_species_code_matches_unicode_name(monkeypatch):
    service = EbirdService()
    ru_key = _normalize_name("Чёрный дрозд")
    service._taxonomy_cache = {
        "ru": {
            "fetched_at": datetime.now(timezone.utc),
            "items": [],
            "index": {ru_key: "tumeru"},
        }
    }
    monkeypatch.setattr(service, "get_taxonomy", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "resolve_locale", AsyncMock(side_effect=lambda loc=None: (loc or "ru").replace("_", "-")))

    code = await service.resolve_species_code("Чёрный дрозд", locale="ru")
    assert code == "tumeru"
