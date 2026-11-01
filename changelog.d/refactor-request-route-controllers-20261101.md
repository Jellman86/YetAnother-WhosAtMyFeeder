- **Explorer reads and Settings addresses are now tested by what they do.** Nothing changes
  on screen. The Explorer's rule that only the newest read may update the page, and the
  Settings rules that turn older addresses such as `/settings#notifications` and
  `/settings/errors` into the tab's own address, moved into small modules with direct
  tests. Browser checks now prove that a slower earlier read cannot replace newer results,
  that a linked capture outside the first page still opens, and that the Settings tab and
  address stay in step through tab choices, Back and old bookmarks. Tests that only
  checked for exact lines of source code were retired once these replaced them.
