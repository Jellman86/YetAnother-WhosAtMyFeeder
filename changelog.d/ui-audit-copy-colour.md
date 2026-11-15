- Colour now means one thing everywhere: amber appears only where something waits on you, green
  where something is confirmed, and the brand blue for everything else. Saved notes, model and
  provider chips, the analysis overlays, the eBird, iNaturalist and video panels in the record, the
  species page's section headings and the notification channel cards lost their amber, cyan,
  indigo and sky tints, and the decorative washes and blurred blobs behind the analysis overlays
  and the start-up screen are gone. Outlines drawn on photographs share one evidence colour. A
  layout test keeps every other colour out unless a component states why it needs one.
- Buttons, headings and labels read in sentence case across the app ("Clear history", "Keyboard
  shortcuts", "Test AI connection") in English and in the translations whose grammar uses it. A
  locale test now fails Title Case labels and em dashes in English fallbacks.
- The detection and Garden records name the subject once, in the rail's heading. The photograph
  no longer repeats it, the common-name card is now a "Change the common name" button, the species
  details button is no longer a second primary action, and the record stops saying that a source
  "was not recorded". The species dialog's sections are headed by words alone, without an icon
  tile beside each heading.
- The review queue offers "Confirm {species}" for every visit the model named, not only for new
  species, so a visit just under the naming threshold is one tap. A decision taken in the queue
  applies only while the visit still reads as it was shown: if another tab or person changed it
  first, nothing is overwritten, the queue says "This visit was changed elsewhere. It now reads
  …" and shows the visit as it is now. The API takes this as `expected_category_name` on
  `PATCH /api/events/{event_id}` and answers `409` when it no longer holds (see `docs/api.md`).
- Every dialog closes with the same round button, the video player is titled by the bird and the
  time instead of the event id, and the keyboard shortcuts panel lists the Explorer's day keys in
  place of the permanent hint on the page. The unexplained "Classification sources" line is gone.
- Clearer words: the error screen says what happened and what to do instead of "Something went
  wrong", empty states say what to do next, Audio history's filters show "Any species" and "Any
  source" instead of sample values, notifications say "Only you see this" in place of a padlock
  and "owner", and a model whose device is not known yet says so in plain words.
- Small labels above headings and groups ("Identified as", the sidebar's "Observe" and "Manage",
  "System status") are no longer spaced-out capitals. They read in sentence case like every other
  label, and the sidebar's group headings now match the Settings rail. A test keeps CSS from forcing
  capitals anywhere.
- A picture that fails to load keeps its place and shows nothing broken: no alt text spilling over
  the controls on it, no broken-image icon. The record's spectrogram keeps its size, says quietly
  that there is no spectrogram for the call, and the call can still be played. On the Leaderboard
  wall a missing picture keeps its cell and names the bird, so nothing on the wall moves.
- The small dots between facts (in the footer, on Explorer cards and elsewhere) now take the colour
  of the text around them, so they meet contrast in both themes, and screen readers no longer read
  them out.
