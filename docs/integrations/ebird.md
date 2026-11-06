# eBird Integration

YA-WAMF integrates with eBird to provide rich context for your bird detections and facilitate data contribution.

## When to enable it
Enable eBird for nearby sightings and notable reports. Species identities and model output labels come from YA-WAMF's local species catalogue; enabling eBird does not replace that catalogue.

## Features
- **Recent Sightings:** See recent observations of the detected species nearby directly in the detection details.
- **Notable Sightings:** Discover rare bird reports in your area.
- **Thumbnail Images:** Notable sightings include species images powered by iNaturalist taxonomy.
- **Export:** Export your detections to a CSV file compatible with eBird's bulk import tool.
- **Range filter:** Optionally set aside identifications of species eBird has never recorded in your region. See [Range filter](../features/range-filter.md).

## Configuration
1. Go to **Settings → Integrations → eBird**.
2. Enable eBird.
3. Enter your eBird API Key.
   *   *Note:* You can request an API key from eBird [here](https://ebird.org/api/keygen).
4. Set a complete latitude/longitude pair under **Settings → Integrations → Location**, then set your search radius and history limit (days).
   *   The radius field uses the unit system chosen in **Settings → Integrations → Location → Display Units**: kilometres for Metric, miles for Imperial and British. eBird accepts 1-50 km (1-31 miles), and YA-WAMF stores the value in kilometres whichever unit you type.

Map popups display externally supplied place names and observation details as
text, preserving their content without interpreting it as HTML.

## Enrichment Behavior
Choose enrichment sources separately under **Settings → Enrichment**. The eBird integration supplies nearby context when configured; it does not automatically override every naming, description or image source. See [Taxonomy & Naming](../features/taxonomy.md).

## Exporting to eBird
YA-WAMF exports a CSV for owner-reviewed import; it does not automatically submit checklists.
Sign in as an owner to export. The file contains precise configured coordinates,
camera names and non-hidden history within your selected date range, so guests
cannot download it. Local CSV export also works with the eBird integration
switched off or without an eBird API key. With application authentication switched
off, requests retain the existing owner-equivalent access.

1. Go to **Settings → Integrations → eBird**.
2. Optionally choose inclusive `From` / `To` dates if you want a bounded checklist range. Leave both blank to export all detections.
3. Click **Export All Sightings (CSV)**.
4. Log in to the [eBird Import Data](https://ebird.org/import) tool.
5. Upload the generated CSV file.
6. Select **eBird Record Format (Extended)**.
7. Review species, dates, location, counts and duration against your actual observations before submitting. Camera detections are not an independent count of individual birds, and the first-to-last detection span is not proof of continuous observation effort.

**Note:** The export now uses the `Stationary` protocol, keeps bird names English-stable for compatibility, and fills duration from the first to last exported detection on each exported date within the selected range. If you set optional location `state` / `country` values in Settings, YA-WAMF will place them into the export instead of leaving those columns blank.
