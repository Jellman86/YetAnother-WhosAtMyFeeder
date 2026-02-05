from app.config import settings


def is_ebird_active() -> bool:
    return bool(settings.ebird.enabled and settings.ebird.api_key)


def get_effective_enrichment_settings() -> dict:
    if is_ebird_active():
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
