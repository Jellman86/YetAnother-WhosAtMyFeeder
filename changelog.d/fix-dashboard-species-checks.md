- The dashboard no longer says "Nothing waiting on you" while the leaderboard's range check is
  waiting on you. **Needs your call** now also names the species the range check flags in the
  last 24 hours, for example "1 species may be misnamed: Red Junglefowl. Only the camera backs it
  and no birder has reported it within 50 km.", and **Open the checks on the Species page** opens
  the leaderboard's Day window at **Needs a check**. For an owner with Garden on, a flagged
  domestic bird offers the same **I keep Chickens: move to Garden** action as the leaderboard.
  While the check is loading or cannot be read, the panel says so rather than claiming nothing is
  waiting, and the day bar's "nothing to review" follows the same rule. Without eBird or a feeder
  location the check does not run, and the panel says only that every visit has a species. A list
  whose refresh failed stays visible, marked as possibly out of date with **Try again**, and a bird
  just moved to Garden is not offered again while the reload is failing.
- `GET /api/leaderboard/species` now reports `nearby_check` (`checked`, `off` or `unavailable`), so
  a client can tell a range check that ran from one that is switched off or failed.
