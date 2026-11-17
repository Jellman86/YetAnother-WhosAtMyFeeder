- Health, Notifications and background jobs now speak of visits, Frigate events, calls and the
  model instead of "detections" and "classifier", in English and German. Health's summary and
  section names are in plainer words ("Naming new visits", "Everything YA-WAMF checks is working").
- An error on Health that YA-WAMF does not recognise now ends in a next step: capture a diagnostics
  bundle and report it. It no longer leaves you with only a technical string.
- The progress of a missed-visits import or a weather fill is written out in your language
  ("10 of 20 checked · 5 visits added · 2 updated · 3 skipped · 0 failed") instead of
  "10/20 • 5 new • 2 upd • 3 skip • 0 err", and a finished job is summed up the same way rather
  than with the server's English sentence.
- A visit that cannot be hidden or deleted now says so and what to try, instead of ending in a raw
  server message.
- The start-up screen now says that start-up carries on without a bird model when none is
  installed, and where to download one.
- Under the hood, 92 strings that nothing displayed were removed from every language.
