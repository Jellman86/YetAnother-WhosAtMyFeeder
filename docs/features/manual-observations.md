# Manual observations

The owner-only **Add observation** page turns a photo or short video into a normal YA-WAMF
observation without requiring a Frigate event. Use it for phone photographs, exported camera
clips, and older wildlife media that you want in the same searchable history as live detections.

## Add an observation

1. Open **Observe → Add observation**.
2. Choose a JPEG, PNG, WebP, MP4, MOV, or WebM file. Images can be up to 25 MB. Videos can be up
   to 250 MB and three minutes long.
3. Let YA-WAMF analyse the media. Images use the normal full-frame-versus-crop path. Videos use
   the same distributed frame sampling, crop comparison, model, and provider as automatic deep
   video classification.
4. Review the leading result and alternatives. Common and scientific names are shown together when
   taxonomy data is available. You can choose a suggestion or enter the correct species,
   observation time, camera/place label, and optional notes.
5. Check the sighting location. For a photo with valid GPS metadata, YA-WAMF places the pin for you.
   You can move it, enter coordinates, or clear it. If the file has no GPS metadata, location stays
   optional and the map lets you add a pin.
6. Select **Save observation**. Nothing is added to detections, counts, or leaderboards before this
   confirmation.

The review step shows the winning input source, model, provider, and confidence when the classifier
reports them. A crop badge means the classifier obtained stronger evidence from a crop; it does not
refer to thumbnail generation.

## Reliability and privacy

- Uploads are owner-only and use the existing authentication boundary.
- The browser rejects files above the documented limits before upload. The bundled monolithic and
  split Nginx configurations allow a bounded 256 MiB multipart request on the exact upload route
  and stream its body to the backend rather than buffering another full copy.
- Files are streamed to disk with explicit size limits, decoded before classification, and rejected
  when the declared format is unsupported or the media cannot be decoded safely.
- GPS is read only from valid image EXIF metadata. Partial, malformed, or out-of-range coordinates
  are ignored. The original upload already contains its metadata; extracted coordinates are kept in
  the owner-only draft and become part of the saved observation only after confirmation.
- A SHA-256 content identity prevents the same file being inserted twice. If a browser reloads,
  the current durable analysis is restored rather than started again.
- Analysis progress and failures are stored in SQLite. A failed analysis can be retried without
  uploading the original again.
- Unsaved drafts expire after seven days and are removed when a later upload begins, preventing
  abandoned large files from accumulating indefinitely.
- Original media and a derived JPEG preview are stored under the persistent `/data` volume. They
  do not depend on Frigate retention or the optional Frigate media cache.
- Uploaded observations use a `manual_…` event identity and are excluded from Frigate missing-media
  reconciliation. Existing snapshot, thumbnail, and clip views serve their persisted local media.
- BirdNET-Go correlation is not requested or displayed for uploaded observations because an upload
  time is not evidence that a nearby microphone heard the same bird.
- Confirmation writes a local observation and its classifier provenance. It does not replay a
  Frigate event or send automatic live-detection integrations and alerts for historical media.
- Deleting a saved manual detection also removes its media and durable workflow record.

Manual observations are included in the normal history and statistics after confirmation. The
`observation_source` API field distinguishes `manual_upload` from `frigate`. Optional
`observation_latitude`, `observation_longitude`, and `observation_location_source` fields retain the
confirmed pin, and the original filename is treated as display metadata rather than a filesystem
path.

## Recovery

If analysis fails, read the inline message and select **Retry analysis**. The original file remains
safe. If the container stopped during analysis, the job becomes retryable rather than silently
creating a partial detection. Use **Start over** to discard an unsaved draft and its media.

An HTTP `413 Request Entity Too Large` before analysis usually means an external reverse proxy is
still applying its default request limit. Allow up to 256 MiB specifically for
`POST /api/manual-observations` and disable request buffering for that route. Keep the backend's
25 MiB image and 250 MiB video limits unchanged; the extra proxy headroom covers multipart fields
and headers. See [Reverse proxy configuration](../setup/reverse-proxy.md) for Nginx examples.

For classifier or provider problems, use **Settings → Detection → Runtime diagnostics**. For model
comparison and hardware validation, see [Model evaluation](model-evaluation.md).
