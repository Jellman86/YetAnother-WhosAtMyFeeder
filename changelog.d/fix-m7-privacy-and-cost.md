- About no longer promises "Nothing leaves your network except the calls listed below" over a list
  that left out Google Fonts and Wikipedia and marked the OpenStreetMap tiles disabled whenever
  eBird was off. The list is now built from the features that send each request, split into what
  this server sends and what each viewer's browser sends, and every row says what it sends. It adds
  Wikipedia, GBIF, Google Fonts, reference photos, the IP-based location lookup, place names,
  BirdWeather, iNaturalist submissions, notification services and model downloads, and a guest is
  told a setting is the owner's to see rather than that it is off.
- Settings → AI no longer shows `$0.00` for a model that has no price. A model without a rate reads
  "Not priced", usage with no prices at all reads "Cost not estimated: add prices", and a total
  states how many requests it covers and which models it leaves out. `/api/stats/ai/usage` reports
  the same coverage ([API](docs/api.md)), and its per-day rows no longer carry a cost that was
  never calculated.
