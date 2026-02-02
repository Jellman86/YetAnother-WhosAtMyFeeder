# eBird Integration

YA-WAMF integrates with eBird to provide rich context for your bird detections and facilitate data contribution.

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

## Exporting to eBird
Since eBird does not provide a public API for submitting checklists programmatically, YA-WAMF provides a CSV export feature compliant with the "Record Format".

1. Go to **Settings > Integrations > eBird**.
2. Click **Export All Sightings (CSV)**.
3. Log in to the [eBird Import Data](https://ebird.org/import) tool.
4. Upload the generated CSV file.
5. Select **eBird Record Format (Extended)**.
6. Verify the data and submit.

**Note:** The export sets the protocol to "Incidental" and duration to "0" by default, as YA-WAMF detections are continuous automated events rather than a dedicated birding session. You may edit the CSV before upload if you wish to group them into specific checklists.
