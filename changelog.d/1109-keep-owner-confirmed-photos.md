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
- **A photo you choose stays chosen, even if the save is interrupted:** Using a photo now marks it as
  your choice before the photo itself is written, and finishes saving it and the record's selected
  photo even if the connection drops part-way. If the save fails, the old photo and its settings are left as
  they were. Refreshing a visit's timing hints no longer drops the choice when its photo settings
  file cannot be read, a video recovery no longer brings back a choice whose photo had gone, and
  caching one capture's photo no longer deletes another capture's chosen photo when their names
  overlap.
- **Storage cleanup is gentler and stops at the limit:** Removing cached files that no longer belong
  to a capture, and removing media older than the history window, no longer hold the database while
  files are deleted, so other saves do not wait for a slow disk; a file that cannot be deleted is
  finished on the next cleanup. Removing media to meet the storage limit or the per-species limit
  still holds it while each capture's files are deleted. The storage limit now weighs only files
  really on disk and counts Garden media as freed only once it is removed, so a missing Garden photo
  no longer pushes out an older bird photo. When a capture is confirmed while cleanup runs, cleanup
  goes on to the next oldest capture until space used is under the limit. A capture you favourite or
  confirm while old media is being removed keeps its media, and its favourite archive waits for it
  rather than recording it as unavailable. If YA-WAMF stops part-way through, the media it had set
  aside goes back when it starts again, before anything reads the cache; where a newer file has
  taken the name meanwhile, the newer file is kept, and one that cannot be put back yet stays set
  aside for the next try and shows in Health. A long cleanup of old media no longer holds up the
  storage limit. Clear cached files pressed while one is running shares that work and still takes
  about as long. Empty-file cleanup no
  longer removes a clip, a recording clip that is still downloading, or a preview while it is being
  written.
- **A photo change that fails after you switch records is reported:** If using, regenerating or
  removing a photo fails after you have opened another record, the error names the species and time
  of the record it was for, instead of disappearing.
- **Regenerating says when it kept the photo:** If regenerating a record's photo keeps the current
  photo, because you chose another photo meanwhile or because the photo's saved settings cannot be
  read, the record now says so and what to do next, instead of reporting a new photo.
