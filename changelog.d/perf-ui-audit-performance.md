- An open page now asks the backend for far less while nothing is happening. A quiet owner page
  used to make 37 to 64 requests a minute (the sidebar's CPU line alone read 24 times a minute);
  it now makes 7 to 13, and the Dashboard 20. Each background reading is taken at the
  rate its source changes: the sidebar CPU line and the Heard card every 15 seconds, camera
  reachability and idle job and analysis status once a minute, backend health every two
  minutes, and the media-folder check every ten. Running work is still followed every five
  seconds, and every reader stops while the tab is hidden and reads once when it is shown again.
- Opening a page reads your settings once instead of two to four times: the shell, the camera
  status control, the Heard card, Audio history and the Settings page share one response.
- The Leaderboard opens with a fraction of the download. Its wall of visits now asks for a
  tile-sized photograph for each small cell
  (`GET /api/about/showcase/{event_id}.jpg?size=tile`, see [the API reference](docs/api.md))
  instead of a card-sized one, a ranking row reads its reference picture when it comes near the
  screen instead of all at once, and the charts below the fold are drawn when you scroll to
  them.
- Settings loads one tab at a time. The Connection, Detection, Notifications, Integrations,
  Security, Data and Beta tabs are now separate files fetched when opened, like Health,
  Enrichment, AI, Appearance and Accessibility already were, so opening Settings no longer
  downloads every tab.
- Pages no longer jump while they load. The footer used to show beneath a page that was still
  reading its data and then leap away; the page area now holds a screen of height. On
  **Settings → Health** the system chart, the status line and the "Updated" reading keep their
  space before they arrive, and the Leaderboard's loading wall is the height of the wall that
  replaces it.
