# Range filter

A wildlife-wide classifier knows birds from every continent, so a feeder on the US west coast is
sometimes told it saw a species that only lives in Europe. The range filter checks each new
automatic identification against the species eBird has ever recorded in your region and sets
aside the ones it has not.

It is **off by default**. Turn it on in **Settings → Detection → Range filter**, then **Apply
Settings**.

## What it needs

| You have | What the filter does |
|---|---|
| A location and an eBird API key | Uses eBird's regional species list for your county, state or country. |
| A location but no eBird key | Nothing. The card says **Add an eBird API key to use range filtering** and links to the key field. |
| BirdNET-Go only | Nothing on its own. Species BirdNET-Go hears count as present, but hearing can never show a species is absent, so it never rejects anything. |
| An approximate location (coordinates to one decimal place) | Uses a state or province list, never a county. |
| Only a country | Uses the country list. |
| No location | Nothing. The switch is disabled and links to **Settings → Integrations → Location**. |

The location and the eBird key are the ones already set under **Settings → Integrations**.

## Where the list comes from

- **Region.** eBird has no reverse geocoder, so the filter asks eBird for the hotspots within
  25 km of your location (sending it the location rounded to about 11 km), and reads the county,
  state and country codes those hotspots carry. The nearest hotspot names your county. Other
  counties with a hotspot within 10 km are combined with it, because near a border the nearest
  hotspot can sit on the wrong side.
- **Species.** The list is eBird's `product/spplist` for that region: every taxon ever reported
  there. Subspecies groups count as their species; "duck sp." and hybrids name no species and
  are dropped.
- **Identity.** eBird's taxonomy gives each species code a scientific name, which resolves to the
  species catalogue's identity exactly, through accepted names and recorded synonyms. Common
  names are never compared.
- **County too short.** A county with fewer than 100 recorded species is under-birded rather than
  species-poor, so its state list is used instead, and the card says so.
- **Refresh.** The list is fetched in the background, never while a detection is being saved. It
  is refreshed weekly while the filter is on, retried every six hours after a failure, and
  refetched when you move the feeder or change **Finest region**. **Refresh list** fetches it now.

## What happens to a bird outside the range

1. If the model's top answer is a species eBird names but has never recorded in your region, the
   model's next answer that *has* been recorded is used instead, as long as it still clears your
   confidence threshold and every other rule (blocked species, the non-bird guard). The record's
   technical details say what the model said first.
2. If no answer qualifies, the detection is not recorded. It is listed under **Recently set
   aside** in the card and in the activity log under **Settings → Health** as *Not recorded,
   never seen in your eBird region*. A genuine vagrant can still be recorded by hand with
   **Add observation**, while Frigate keeps the clip.

The same rule applies to backfill and to **Reclassify**. A video or high-quality-photo refinement
that names an out-of-range species is recorded in its own fields but never replaces the
identification.

## When nothing is filtered

The filter fails open. It filters nothing, and the card says why, when:

- there is no list yet, or the last fetch failed (eBird unreachable, key rejected, no region
  found);
- the list is more than 30 days old;
- the list is for a different location or region level;
- the stored list fails its checks (empty, implausibly large, or under half of it matches the
  species catalogue);
- a label has no exact catalogue identity, or names a species eBird does not use. The card
  counts these: *N model labels could not be matched to eBird and are never filtered*.

Species you choose yourself, through a manual tag, a correction or **Add observation**, are never
filtered.

## Limits

- **Seasons.** eBird's regional list covers all seasons and all years together. A summer visitor
  counts as present all year, and the filter cannot catch a species that is in your region but
  out of season.
- **Vagrants.** A region's all-time list includes past vagrants, so it is wider than the birds you
  will normally see. That keeps genuine rarities from being lost, at the cost of filtering less.
- **History.** Only new admissions are checked. Nothing already recorded is changed; the preview
  only lists recent detections that the filter *would* have set aside.

## Privacy and safety

- The eBird key travels only in the `X-eBirdApiToken` header to `api.ebird.org`. It is never part
  of a URL, a log line or an error message.
- eBird receives your location rounded to about 11 km. The nearest hotspot is chosen on this host.
- Every eBird request has a time limit and a size limit, and the stored list is validated each
  time it is loaded.

## API

See [Range filter](../api.md#range-filter) in the API reference.
