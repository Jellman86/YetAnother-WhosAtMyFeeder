- **"Frigate could not be reached" messages no longer repeat your Frigate address in full.**
  When a photo, clip, timeline preview or live stream cannot be fetched because Frigate is down,
  visitors now see a plain "Could not reach Frigate. Try again in a moment." with no address at
  all. As the owner you still see which Frigate was tried, shortened to `scheme://host:port`, so a
  username, password, token or private path in a reverse-proxy URL is never shown. The Frigate
  and BirdNET-Go connection tests, the owner connectivity check, the notification test and
  eBird searches follow the same rule.
- **Logs keep integration credentials out of error lines.** Frigate, Home Assistant, media-probe
  and unexpected-error log lines reduce any address in an HTTP error to `scheme://host:port`
  and hide `token=`-style values, including in the logged traceback.
