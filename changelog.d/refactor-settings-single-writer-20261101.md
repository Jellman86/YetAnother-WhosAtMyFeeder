- **A settings save can no longer undo or leak another change made at the same moment.**
  Activating a model, the startup replacement of a retired model, first-run setup and the
  telemetry identity now save through the same ordered, persist-then-publish path as
  **Apply Settings**, so a save already in progress cannot revert them, and a failed save
  leaves the running settings unchanged. Testing a Discord, Pushover or Telegram channel
  with credentials typed but not applied no longer places them on the running settings,
  where a concurrent save could have written them to `config.json`.
