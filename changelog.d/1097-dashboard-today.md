- **The Dashboard has a Today window.** Beside the heading, choose **Today** to see what has
  visited since your local midnight, or **Last 24 hours** (still the default, so an early morning
  is never empty). Each device remembers its choice. Every figure, the field log, Garden visits,
  the activity chart, the Heard card, the species checks and **Needs your call** count the same
  window, so the waiting captures agree with the **Unresolved** figure. A new species still waits
  for you whenever it was first seen in the last fortnight. The field log's earlier-visits line
  opens the Explorer on the same window, and on Today it reads "earlier visits today". "Open the
  checks on the Leaderboard" opens the Leaderboard's Today too. While the new window is read,
  nothing from the old one is shown under its name. An open Dashboard reads the new day at
  midnight, and a read that crosses midnight is asked again rather than showing one day's figures
  beside the other's visits or calls. An open review walkthrough takes the new day's list. When a
  guest's shared history starts after their midnight, the Dashboard says from what time Today is
  shown.
- **Visits after midnight land in the right hour in every time zone.** In zones a half or three
  quarters of an hour off UTC, such as India or Newfoundland, the day summary's hourly counts filed
  a capture just after midnight under 23:00 the day before. Each capture is now counted in the local
  hour it was made in.
- **The Explorer's periods match the rest of the app.** **Week** and **Month** are now **Last 7
  days** and **Last 30 days**, and they cover exactly 7 and 30 calendar days including today. They
  used to cover 8 and 31. Links that use `date=week` and `date=month` still work.
- **The Dashboard no longer says "nothing" when it could not look.** A refresh that fails after an
  empty reading now says the visits could not be loaded. With Garden visits unreadable, an empty
  log says "No bird visits", and the Heard card says when its calls could not be loaded instead of
  "No calls heard".
- **The day's counts share one window edge.** The day summary and Needs your call now count from
  `window_start` up to, but not including, `window_end`, so a capture made at that instant is
  counted once, by the next read, in every figure.
- **The Explorer reads Today again on the new day.** Reading the same period again after midnight
  now asks for the new day's dates instead of the day the page was opened on.
