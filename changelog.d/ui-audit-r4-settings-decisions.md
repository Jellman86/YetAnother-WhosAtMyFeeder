- **Settings › Models now says, in one sentence, what names your birds right now.** For example
  "Naming birds with Birds of your region, quick on Intel GPU.", or "Nothing is naming birds yet:
  … is not on this install." when the chosen model's files are missing. The first-run wizard's
  model step and About show the same sentence, so the three never disagree. The four-column strip
  of runtime facts is gone; a link appears only when the runtime report has something to check.
- **The identification model is chosen around one decision.** Models shows the model in use and,
  while the install still runs the small starter model or nothing, one recommended next model.
  The Hardware device choice is labelled **Identification model runs on**, and the two device
  checks say what they cover (**Check devices for every installed model**, **Check devices for the
  bird finder**). The rest of the catalogue waits behind a single **Choose another model** disclosure (the second
  "Show all models" toggle is gone), and a row opens its details in place. Models are named by
  what they are for ("Birds and wildlife, balanced"), with the code name beside it, and their
  coverage, download size and memory are one line in plain words.
- **No model is called built in unless it really ships with your install.** The "Built-in
  fallback" group is now "Small and quick", and `GET /api/models/installed` marks a model with
  `bundled: true` only when it comes from the image, so a model that still needs downloading is
  never labelled built in.
- **A model that failed to load is never reported as naming birds.** The status sentence says it
  is installed but failed to load, with the cause in plain words and the runtime's own message
  under Technical details (not on About).
- **Maintenance says when each job last ran and what it found**, from a durable record that
  survives a restart (new owner-only `GET /api/maintenance/last-runs`). A timezone scan whose
  Frigate lookups failed says it could not check them and asks for another scan, instead of
  reporting that nothing needs a repair, and a running backfill says when it started. Each job says when to run
  it and what it changes, **Apply timezone repair** says why it is disabled ("Scan first", or
  "Nothing to repair" when the last scan found nothing), Missed detections reads "Skipped" and
  "Failed" in full, and times follow the app's own date and 12/24-hour settings.
- **Settings › Data has one storage budget.** **Limit the space photos and video use** is a
  switch with a size in GB, with one sentence of what the rules add up to; the two per-species
  limits moved under advanced options, each with its own switch, so "0 means off" no longer has
  to be typed. An emptied or out-of-range size is refused with a reason and the saved limit kept,
  never replaced by a small one. The summary names every rule that removes media, the per-species
  cap included. Archived favourites wait for a measurement instead of showing 0.
- **Beta features: the two Garden sliders say what each decides** ("Suggest a motion photo when
  this sure it shows an animal", "Name an animal when this sure which one it is"), and Collection
  status is a few plain sentences that name what is stopping the first check.
- **The unsaved-changes bar is one line and two buttons**, with the save rule behind **How saving
  works**, so it no longer covers most of a phone at 200 % text. When a change was also saved
  elsewhere, the bar shows both values ("Saved elsewhere: … · Yours: …") beside the choice.
