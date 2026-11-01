- **Translations are now authored one file per area, so features stop colliding in one huge file.**
  Nothing changes on screen. Each language's strings moved from a single file of about 4,200 lines
  into one file per top-level domain under `apps/ui/src/lib/i18n/locales/<language>/`, for example
  `en/settings.json`, `en/events.json` and `en/garden.json`. Every key name and every string is
  unchanged in all nine languages, and each language still loads as one lazily fetched file.
  English is always loaded alongside the chosen language, and a new test proves that a key missing
  from any translation shows the English text rather than the raw key. A new check rejects a domain
  file that repeats a key, which a clean-looking merge could otherwise hide.
