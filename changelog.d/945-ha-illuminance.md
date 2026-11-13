- You can now record the measured light level with each detection (#945). Name a lux sensor
  under **Settings → Integrations → Home Assistant weather → Illuminance entity** and each new
  detection keeps its reading, shown in the record's **Conditions** row ("Light 1,240 lx"), in
  the API as `illuminance_lux`, and in the eBird export's species comment. The value is only
  ever a measurement: `unknown`, `unavailable`, a value that is not a number or is outside 0 to
  200,000 lx, and an entity that is not an illuminance sensor all store nothing, and it is
  never estimated from the forecast. Once stored it is not rewritten, so changing the sensor
  later leaves history alone. **Fetch a live reading** now shows the light level on its own
  line, or the reason there is none. See
  [Home Assistant](docs/integrations/home-assistant.md#weather-and-light-from-your-own-sensors).
- With only an illuminance entity named for Home Assistant, and no weather entity or sensor
  override, weather now keeps coming from the forecast provider instead of being left empty.
