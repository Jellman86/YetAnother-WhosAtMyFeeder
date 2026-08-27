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
    monkeypatch.setattr(
        service, "resolve_locale", AsyncMock(side_effect=lambda loc=None: (loc or "ru").replace("_", "-"))
    )

    code = await service.resolve_species_code("Чёрный дрозд", locale="ru")
    assert code == "tumeru"


# ── Locale resolution ────────────────────────────────────────────────────────
#
# eBird publishes its locale codes with underscores (`pt_BR`, `zh_SIM`). Measured
# against the live endpoint on 2026-08-19: `pt` is not a supported code at all,
# and `zh` is supported but carries only 7.1% of names translated against
# `zh_SIM`'s 30.8%.

EBIRD_LOCALE_CODES = [
    "en",
    "de",
    "es",
    "fr",
    "it",
    "ja",
    "ru",
    "pt_AO",
    "pt_BR",
    "pt_PT",
    "pt_RAA",
    "pt_RAM",
    "zh",
    "zh_HK",
    "zh_SIM",
]


@pytest.fixture
def locale_service(monkeypatch):
    from app.services.ebird_service import EbirdService

    service = EbirdService()
    monkeypatch.setattr(service, "is_configured", lambda: True)

    async def supported():
        return set(EBIRD_LOCALE_CODES)

    monkeypatch.setattr(service, "_get_supported_locales", supported)
    return service


@pytest.mark.asyncio
async def test_portuguese_resolves_to_a_portuguese_locale_not_english(locale_service):
    """`pt` is not an eBird code, so it used to fall through to English."""
    assert await locale_service.resolve_locale("pt") == "pt_BR"


@pytest.mark.asyncio
async def test_chinese_resolves_to_the_variant_that_is_actually_translated(locale_service):
    assert await locale_service.resolve_locale("zh") == "zh_SIM"


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["de", "es", "fr", "it", "ja", "ru", "en"])
async def test_a_language_ebird_supports_directly_is_left_alone(locale_service, code):
    assert await locale_service.resolve_locale(code) == code


@pytest.mark.asyncio
async def test_an_explicit_regional_choice_is_honoured(locale_service):
    assert await locale_service.resolve_locale("pt_PT") == "pt_PT"
    assert await locale_service.resolve_locale("zh_HK") == "zh_HK"


@pytest.mark.asyncio
async def test_a_hyphenated_request_matches_an_underscored_code(locale_service):
    """Browsers and settings emit `pt-BR`; eBird publishes `pt_BR`."""
    assert await locale_service.resolve_locale("pt-BR") == "pt_BR"
    assert await locale_service.resolve_locale("ZH-sim") == "zh_SIM"


@pytest.mark.asyncio
async def test_an_unknown_regional_variant_falls_back_within_its_language(locale_service):
    assert await locale_service.resolve_locale("pt_XX") == "pt_BR"


@pytest.mark.asyncio
async def test_an_unsupported_language_falls_back_to_english(locale_service):
    assert await locale_service.resolve_locale("xx") == "en"
    assert await locale_service.resolve_locale("") == "en"
