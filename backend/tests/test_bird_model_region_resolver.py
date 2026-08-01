from app.services.bird_model_region_resolver import resolve_bird_model_region


def test_resolve_bird_model_region_prefers_manual_override():
    assert resolve_bird_model_region(country="GB", override="na") == "na"


def test_resolve_bird_model_region_uses_country_when_auto():
    assert resolve_bird_model_region(country="GB", override="auto") == "eu"
    assert resolve_bird_model_region(country="US", override="auto") == "na"


def test_resolve_bird_model_region_accepts_persisted_country_names_and_iso3_codes():
    assert resolve_bird_model_region(country="United Kingdom", override="auto") == "eu"
    assert resolve_bird_model_region(country="  united   kingdom  ", override="auto") == "eu"
    assert resolve_bird_model_region(country="GBR", override="auto") == "eu"
    assert resolve_bird_model_region(country="United States", override="auto") == "na"
    assert resolve_bird_model_region(country="USA", override="auto") == "na"
    assert resolve_bird_model_region(country="Canada", override="auto") == "na"


def test_resolve_bird_model_region_accepts_supported_european_country_names():
    assert resolve_bird_model_region(country="Germany", override="auto") == "eu"
    assert resolve_bird_model_region(country="Czech Republic", override="auto") == "eu"
    assert resolve_bird_model_region(country="The Netherlands", override="auto") == "eu"


def test_resolve_bird_model_region_falls_back_when_location_unknown():
    assert resolve_bird_model_region(country=None, override="auto") == "na"
    assert resolve_bird_model_region(country="ZZ", override="auto") == "na"
