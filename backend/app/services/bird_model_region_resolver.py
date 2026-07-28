EU_COUNTRIES = {
    "AT",
    "BE",
    "BG",
    "CH",
    "CY",
    "CZ",
    "DE",
    "DK",
    "EE",
    "ES",
    "FI",
    "FR",
    "GB",
    "GR",
    "HR",
    "HU",
    "IE",
    "IS",
    "IT",
    "LT",
    "LU",
    "LV",
    "MT",
    "NL",
    "NO",
    "PL",
    "PT",
    "RO",
    "SE",
    "SI",
    "SK",
}

NA_COUNTRIES = {"US", "CA"}

# Location settings are populated by reverse geocoding and therefore normally
# contain a human-readable country name, while older/manual configurations may
# contain an ISO-2 or ISO-3 code. Keep the resolver independent of optional
# geocoding packages and normalize every representation the application itself
# can persist.
COUNTRY_ALIASES = {
    "AUSTRIA": "AT",
    "AUT": "AT",
    "BELGIUM": "BE",
    "BEL": "BE",
    "BULGARIA": "BG",
    "BGR": "BG",
    "SWITZERLAND": "CH",
    "CHE": "CH",
    "CYPRUS": "CY",
    "CYP": "CY",
    "CZECHIA": "CZ",
    "CZECH REPUBLIC": "CZ",
    "CZE": "CZ",
    "GERMANY": "DE",
    "DEU": "DE",
    "DENMARK": "DK",
    "DNK": "DK",
    "ESTONIA": "EE",
    "EST": "EE",
    "SPAIN": "ES",
    "ESP": "ES",
    "FINLAND": "FI",
    "FIN": "FI",
    "FRANCE": "FR",
    "FRA": "FR",
    "UNITED KINGDOM": "GB",
    "GREAT BRITAIN": "GB",
    "UK": "GB",
    "GBR": "GB",
    "GREECE": "GR",
    "GRC": "GR",
    "CROATIA": "HR",
    "HRV": "HR",
    "HUNGARY": "HU",
    "HUN": "HU",
    "IRELAND": "IE",
    "IRL": "IE",
    "ICELAND": "IS",
    "ISL": "IS",
    "ITALY": "IT",
    "ITA": "IT",
    "LITHUANIA": "LT",
    "LTU": "LT",
    "LUXEMBOURG": "LU",
    "LUX": "LU",
    "LATVIA": "LV",
    "LVA": "LV",
    "MALTA": "MT",
    "MLT": "MT",
    "NETHERLANDS": "NL",
    "THE NETHERLANDS": "NL",
    "NLD": "NL",
    "NORWAY": "NO",
    "NOR": "NO",
    "POLAND": "PL",
    "POL": "PL",
    "PORTUGAL": "PT",
    "PRT": "PT",
    "ROMANIA": "RO",
    "ROU": "RO",
    "SWEDEN": "SE",
    "SWE": "SE",
    "SLOVENIA": "SI",
    "SVN": "SI",
    "SLOVAKIA": "SK",
    "SLOVAK REPUBLIC": "SK",
    "SVK": "SK",
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
    "USA": "US",
    "U.S.": "US",
    "U.S.A.": "US",
    "CANADA": "CA",
    "CAN": "CA",
}

SUPPORTED_BIRD_MODEL_REGIONS = {"auto", "eu", "na"}
DEFAULT_BIRD_MODEL_REGION = "na"


def normalize_bird_model_region(value: str | None) -> str:
    normalized = (value or "auto").strip().lower()
    return normalized if normalized in SUPPORTED_BIRD_MODEL_REGIONS else "auto"


def resolve_bird_model_region(*, country: str | None, override: str | None) -> str:
    normalized_override = normalize_bird_model_region(override)
    if normalized_override != "auto":
        return normalized_override

    normalized_country = " ".join((country or "").strip().upper().split())
    normalized_country = COUNTRY_ALIASES.get(normalized_country, normalized_country)
    if normalized_country in EU_COUNTRIES:
        return "eu"
    if normalized_country in NA_COUNTRIES:
        return "na"
    return DEFAULT_BIRD_MODEL_REGION
