- BirdNET catalogue identity resolution runs off the event loop before a history
  write starts, keeping other requests responsive while a catalogue is checked or
  reloaded. Unavailable, unknown or ambiguous identities still permit audio ingest.
