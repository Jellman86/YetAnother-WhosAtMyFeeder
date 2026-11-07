- **Small Birds and Medium Birds activate after a fresh download again.** Since v2.22.0 these models
  read their species names from the catalogue, so a new download has no `labels.txt`, but activation
  still asked for that file and stopped with "model files are missing or incomplete". Activation and
  the installed-model list now check the regional model actually on disk.
