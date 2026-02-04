from app.config import settings


def has_ebird_key() -> bool:
    return bool(settings.ebird.api_key)


def get_effective_enrichment_settings() -> dict:
    if has_ebird_key():
        return {
            "mode": "per_enrichment",
            "single_provider": "ebird",
            "summary_source": "ebird",
            "taxonomy_source": "ebird",
            "sightings_source": "ebird",
            "seasonality_source": "inaturalist",
            "rarity_source": "ebird",
            "links_sources": ["ebird", "wikipedia", "inaturalist"],
        }

    return {
        "mode": "per_enrichment",
        "single_provider": "wikipedia",
        "summary_source": "wikipedia",
        "taxonomy_source": "inaturalist",
        "sightings_source": "disabled",
        "seasonality_source": "inaturalist",
        "rarity_source": "disabled",
        "links_sources": ["wikipedia", "inaturalist"],
    }
