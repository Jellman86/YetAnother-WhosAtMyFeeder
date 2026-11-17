- The setup wizard is in plainer words. The model step asks you to "check it runs on this machine"
  instead of "validate on my hardware", and lists "devices" rather than "providers available in
  this image". The cameras step no longer quotes Frigate's `min_score / threshold /
  min_initialized` settings: it says that Frigate decides which snapshots it sends. Importing
  history speaks of visits, and sign-in speaks of the owner rather than an admin.
- About says what is kept "in one file in your data folder" rather than "SQLite under /data", calls
  the naming step "Model", and its list of outside services speaks of visits. Durations and sizes
  on About, in the wizard and in Model evaluation no longer split from their unit at a line end,
  in every language.
