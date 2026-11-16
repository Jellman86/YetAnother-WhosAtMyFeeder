- About no longer promises "Nothing leaves your network except the calls listed below" over a list
  that left out Google Fonts and Wikipedia and marked the OpenStreetMap tiles disabled whenever
  eBird was off. The list is now built from the conditions under which each request is really
  made, and every row says what it sends:
  - three groups: what this server sends, what each viewer's browser sends, and what happens only
    when you connect an account, press a test button or run diagnostics;
  - usage statistics and health reports are separate rows, because health reports send with usage
    statistics off; Garden alerts have their own row, because they can use their own channels with
    every bird channel off;
  - a switch that cannot send is not shown as on: AI needs a saved key, BirdWeather a station
    token, iNaturalist submissions a connected account;
  - coordinates are disclosed wherever they are sent (weather, eBird, BirdWeather, iNaturalist's
    local data), and AI and notification rows list the classes of data they carry;
  - model downloads name Google Storage as well as GitHub, and the startup repair of a model's
    missing configuration file is listed;
  - states read On, Off, Always or When used, and a guest is told a setting is the owner's to see
    rather than that it is off.
- Settings → AI no longer shows `$0.00` for a model that has no price. A model without a rate reads
  "Not priced", usage with no prices at all reads "Cost not estimated: add prices", and a total
  states how many requests it covers and which models it leaves out. `/api/stats/ai/usage` reports
  the same coverage ([API](docs/api.md)), and its per-day rows no longer carry a cost that was
  never calculated.
