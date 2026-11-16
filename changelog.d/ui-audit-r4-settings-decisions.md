- **Settings › Models now says, in one sentence, what names your birds right now.** For example
  "Naming birds with Birds of your region, quick on Intel GPU.", or "Nothing is naming birds yet:
  … is not on this install." when the chosen model's files are missing. The first-run wizard's
  model step and About show the same sentence, so the three never disagree. The four-column strip
  of runtime facts is gone; a link appears only when the runtime report has something to check.
- **The identification model is chosen around one decision.** Models shows the model in use and,
  while the install still runs the small starter model or nothing, one recommended next model.
  The rest of the catalogue waits behind a single **Choose another model** disclosure (the second
  "Show all models" toggle is gone), and a row opens its details in place. Models are named by
  what they are for ("Birds and wildlife, balanced"), with the code name beside it, and their
  coverage, download size and memory are one line in plain words.
- **No model is called built in unless it really ships with your install.** The "Built-in
  fallback" group is now "Small and quick", and `GET /api/models/installed` marks a model with
  `bundled: true` only when it comes from the image, so a model that still needs downloading is
  never labelled built in.
- **Maintenance says when each job last ran and what it found**, from a durable record that
  survives a restart (new owner-only `GET /api/maintenance/last-runs`). Each job says when to run
  it and what it changes, **Apply timezone repair** says why it is disabled ("Scan first" or "The
  scan found nothing to repair"), and times follow the app's own date and 12/24-hour settings.
- **Settings › Data has one storage budget.** **Limit the space photos and video use** is a
  switch with a size in GB, with one sentence of what the rules add up to; the two per-species
  limits moved under advanced options, each with its own switch, so "0 means off" no longer has
  to be typed. Archived favourites wait for a measurement instead of showing 0.
- **Beta features: the two Garden sliders say what each decides** ("Suggest a motion photo when
  this sure it shows an animal", "Name an animal when this sure which one it is"), and Collection
  status is a few plain sentences that name what is stopping the first check.
- **The unsaved-changes bar is one line and two buttons**, with the save rule behind **How saving
  works**, so it no longer covers most of a phone at 200 % text. When a change was also saved
  elsewhere, the bar shows both values ("Saved elsewhere: … · Yours: …") beside the choice.
