# Taxonomy & Naming

YA-WAMF uses a professional taxonomy engine to ensure every bird sighting is recorded with both its common and scientific identity.

## iNaturalist Integration
The system is connected to the [iNaturalist API](https://www.inaturalist.org/). Every time a new species is detected, YA-WAMF:
1. Performs a bidirectional lookup (Common ↔ Scientific).
2. Retrieves the standard Taxonomic ID.
3. Caches the result in a local SQLite table (`taxonomy_cache`) to avoid redundant API calls.

## Display Modes
You can customize how birds are named in the UI via **Settings > Detection**:

- **Standard:** Common name is primary, Scientific name is the subtitle.
- **Hobbyist:** Scientific name is primary, Common name is the subtitle.
- **Strictly Scientific:** Only the Scientific name is shown.

![Species List](../images/frontend_species.png)

## Taxonomy Repair
If your database has old detections with inconsistent naming, you can run the **Taxonomy Repair** tool in the settings. This tool will scan your entire history and normalize all labels against the iNaturalist database.
