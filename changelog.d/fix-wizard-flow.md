- **Setup picks up where you left it.** Reloading or closing the page part way through used to drop you
  on the Dashboard with no sign setup was unfinished. The wizard now returns to the step you reached,
  after signing in if you set a password, until you finish or skip it.
- **Review goes back to Review.** In the setup wizard, opening a section from the summary now returns
  to the summary instead of walking through every later step.
- **A failed Frigate test explains the token.** The Connection step now says how to set
  `FRIGATE_AUTH_TOKEN` when Frigate cannot be reached, since a Frigate that requires a sign-in fails
  that test.
