- **Pages read only what they show.** Opening About, Notifications or a Settings tab no longer
  reads the recent detection history; the Dashboard, which shows it, reads it when it opens.
  Health builds its timeline from its own visit reading and no longer reads the history at all.
  Each Settings tab reads its own helper data when it is first opened: the BirdNET-Go sources on
  Integrations, the recording-clip check on Connection, and the backfill status on Data. A
  backfill that is running is still followed on every tab, so its end is announced wherever you
  are, but the page learns that from the pushed status instead of asking on every tab.
- **A visitor's sidebar CPU line samples once a minute**, down from four times; an owner's line
  already follows the pushed status and makes no requests.
