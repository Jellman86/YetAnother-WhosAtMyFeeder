# eBird Integration

YA-WAMF integrates with eBird to provide rich context for your bird detections and facilitate data contribution.

## Recommendation
We strongly recommend enabling eBird for all users. It provides the most complete taxonomy and sightings context in YA-WAMF, improves species naming consistency across the UI, and makes your data export-ready with minimal effort.

## Features
- **Recent Sightings:** See recent observations of the detected species nearby directly in the detection details.
- **Notable Sightings:** Discover rare bird reports in your area.
- **Thumbnail Images:** Notable sightings include species images powered by iNaturalist taxonomy.
- **Export:** Export your detections to a CSV file compatible with eBird's bulk import tool.

## Configuration
1. Go to **Settings > Integrations**.
2. Enable eBird.
3. Enter your eBird API Key.
   *   *Note:* You can request an API key from eBird [here](https://ebird.org/api/keygen).
4. Set your search radius (km) and history limit (days).

## Enrichment Behavior
When eBird is enabled, YA-WAMF will prefer eBird taxonomy and recent sightings for enrichment wherever available. If eBird data is unavailable for a species or you disable eBird, YA-WAMF falls back to iNaturalist and Wikipedia sources where appropriate.

## Exporting to eBird
Since eBird does not provide a public API for submitting checklists programmatically, YA-WAMF provides a CSV export feature compliant with the "Record Format".

1. Go to **Settings > Integrations > eBird**.
2. Optionally choose an export date if you want a single-day checklist file.
3. Click **Export All Sightings (CSV)**.
4. Log in to the [eBird Import Data](https://ebird.org/import) tool.
5. Upload the generated CSV file.
6. Select **eBird Record Format (Extended)**.
7. Verify the data and submit.

**Note:** The export now uses the `Stationary` protocol, keeps bird names English-stable for compatibility, and fills duration from the first to last exported detection on each exported date. If you set optional location `state` / `country` values in Settings, YA-WAMF will place them into the export instead of leaving those columns blank.
