- **Status lights only claim what was measured.** The sidebar's live tile and the Dashboard's
  feed line now show **Live** only while the MQTT broker session is actually up. A broker that
  cannot be reached reads **No events**, a Frigate that does not answer reads **No Frigate**, and a
  visitor (who is never told the broker's state) sees **Connected**, meaning only that the page
  reached YA-WAMF. Changes are pushed to open owner pages as they happen.
- **Settings → Health no longer says "healthy" while the broker or Frigate is down.** The verdict
  names the connection that failed and what to check, the MQTT card leads with the connection
  (address, last attempt and the broker client's own error) instead of queue load, and a new
  Frigate card says whether Frigate answered the latest request. `GET /health` reports `degraded`
  in those cases too, and the new owner endpoint `GET /api/diagnostics/connections` carries the
  measured state (see [the API reference](docs/api.md#debug-owner)).
- **The Garden review link opens the captures waiting for review.** Opening
  `/events?visitors=garden&review=pending` (or an old `/garden` link) read bird visits before the
  owner settings had loaded, then labelled them an empty Garden queue ("No Garden captures need
  review" above "Showing 1-24 of 725"). The Explorer now waits for those settings before its first
  read.
- **The setup review is honest about access and connections.** Running without a password shows
  **No password** instead of a green **Configured**, and saved Frigate and MQTT addresses that
  cannot be reached show **Not reachable** rather than **Configured**.
- **About no longer shows "Running for: unknown" beside an uptime figure.** The start time is read
  even while a startup warning makes the readiness check answer 503, and an availability window
  that was only partly recorded says how many hours the percentage covers.
- **The Frigate and MQTT connection test runs both checks.** A Frigate failure no longer marks the
  independent MQTT check "not run", and the summary names which checks failed instead of repeating
  the first error.
