EU_COUNTRIES = {
    "AT", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB",
    "GR", "HR", "HU", "IE", "IS", "IT", "LT", "LU", "LV", "MT", "NL", "NO", "PL",
    "PT", "RO", "SE", "SI", "SK",
}

NA_COUNTRIES = {"US", "CA"}

SUPPORTED_BIRD_MODEL_REGIONS = {"auto", "eu", "na"}
DEFAULT_BIRD_MODEL_REGION = "na"


def normalize_bird_model_region(value: str | None) -> str:
    normalized = (value or "auto").strip().lower()
    return normalized if normalized in SUPPORTED_BIRD_MODEL_REGIONS else "auto"


def resolve_bird_model_region(*, country: str | None, override: str | None) -> str:
    normalized_override = normalize_bird_model_region(override)
    if normalized_override != "auto":
        return normalized_override

    normalized_country = (country or "").strip().upper()
    if normalized_country in EU_COUNTRIES:
        return "eu"
    if normalized_country in NA_COUNTRIES:
        return "na"
    return DEFAULT_BIRD_MODEL_REGION
