- **Settings has an Integrations section and a Notifications section.** Integrations holds every
  other service in one place: BirdNET-Go, Home Assistant weather, eBird, iNaturalist, BirdWeather
  and the AI provider. Each has its own switch and its own test, and says its state in words under
  its name: off, on but not set up (with what is missing), not tested on this visit, or the result
  of the last test with its time. Notifications replaces Alerts and holds when you are told about a
  visit, every channel, and Garden animal alerts.
- **What was left of Sharing & integrations is now Access & privacy:** sign-in, guest access and
  telemetry, all on its first screen.
- **Your feeder's location is in Cameras & connection,** after the cameras. It is the section
  Settings opens on, and the weather, eBird, iNaturalist and the range filter all read it.
- **Discord, Pushover and Telegram each have a Send the photo switch.** Sending text only used to
  need `NOTIFICATIONS__<CHANNEL>__INCLUDE_SNAPSHOT=false` in the environment. `/api/settings`
  carries `notifications_discord_include_snapshot`, `notifications_pushover_include_snapshot` and
  `notifications_telegram_include_snapshot`.
- **Custom notification rules can be set in Settings.** **Custom rules** is now a choice in the
  Notifications sentence, with three switches under it: alert when a visit starts, alert later if
  none has gone yet, and wait for the video check. Custom rules send at most one alert per visit,
  and the copy says so. On any other choice the switches are shown disabled, because those modes
  set their own triggers. An install whose mode was `custom` could see that but had nowhere to
  change it.
- **An integration's test result stays on its card** when you open another section and come back,
  until you change a value it ran with or reload the page.
- **Old Settings links still work.** `/settings/alerts` opens Notifications, `/settings/sharing`
  opens Access & privacy, and `/settings/sharing#integrations` or `#ai` opens that place in
  Integrations. Search finds every moved setting where it is now.
- **Messages that send you to a setting name its real place.** Sentences that pointed at
  "Sharing & integrations → Location", "Settings › Models › Hardware" or "this tab" now take the
  section's name from the navigation itself, in every language, so they cannot go stale again.
- **The status column and the sidebar say Notifications,** not Alerts, to match the section.
