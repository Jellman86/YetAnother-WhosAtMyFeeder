- **Photos you confirmed or chose are kept (#1109):** Captures you confirmed, and captures whose
  photo you chose, now keep their main photograph when the storage limit, the per-species limit or
  age cleanup removes media. Their clips, previews and other photo choices can still go. A photo
  already deleted before this change cannot be recovered once Frigate no longer has it. Settings →
  Storage & upkeep now says that space used stays above the storage limit when favourites and kept
  photographs alone take more, and both per-species limits now say that they count captures, not
  visits. Using a photo that is missing or cannot be read is refused before the current photograph
  is replaced ([`POST /api/frigate/{event_id}/snapshot/apply`](docs/api.md)).
- **Thumbnails follow a photo change at once:** Choosing or regenerating a photograph in a record
  now refreshes its thumbnails in Explorer without reloading the page, even when you open another
  record before it finishes. That other record's photo controls stay usable meanwhile, and no
  longer stay locked when a photo removal finishes after you switch.
