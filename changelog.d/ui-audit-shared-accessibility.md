- **Keyboard focus is easy to see in both themes.** Every shared control now draws one opaque
  focus ring that stands out from whatever is beside it (3:1 or better against the page, a panel
  and a tinted row, in the light and dark modes of both colour themes). The old ring was a
  half-transparent tint that measured 1.6:1 on white. The ring appears for keyboard focus and no
  longer flashes on a mouse click. Controls over a photograph or in the video player use a lighter
  ring that reads on a dark ground.
- **Small print is larger and darker.** No text is set under 12px any more: at the Standard text
  size the smallest labels were 9.6px. Helper text, timestamps, captions and coloured small text
  across the Dashboard, Explorer, Leaderboard, Audio history, Notifications, About and the record,
  species and review dialogs now meet 4.5:1 on the ground they actually sit on, tinted rows and
  the page background included.
- **Buttons are a comfortable size by default.** A kit button is at least 44px tall with its own
  padding, so a button can no longer shrink to a sliver.
- **Screen readers hear what the screen shows.**
  - The sidebar status is a real list inside a live region, and its **System health** link is
    named by its own words; the status tiles keep their tooltips.
  - Rows and buttons on the Dashboard, Leaderboard, Audio history, species page and video player
    are named by the words on them instead of a hidden label that left those words out.
  - The record's **Delete** and **Hide** actions are labelled buttons, not two unnamed icons
    told apart by colour.
  - Map pins, the setup and diagnostic progress bars and the video player's share fields have
    names; map pins are 24px targets.
  - The sign-in screen has a main landmark, the skip link always has a target, the phone header
    is a page banner, and About and Audio history use valid definition lists and heading levels.
  - The page declares the language you picked, so a screen reader pronounces it correctly.
- **A check result states each outcome once.** Test dialogs no longer repeat a failed step's
  sentence in the summary box; the summary names which checks did not pass (or that all passed).
- **Nothing moves or changes by itself in the footer.** The bird fact is chosen once per page
  load instead of turning over every eight seconds, and it is no longer amber, which is kept for
  work that needs you.
- **Words over photographs stay legible.** Time, score and camera labels on Explorer cards and
  the Leaderboard wall sit on a darker, unblurred fill; share-bar labels on the Leaderboard pick
  the ink that reaches 4.5:1 on every segment colour.
- **Long labels are shown whole.** Sidebar navigation labels wrap instead of being cut off
  (German "Beobachtung hinzufügen"), including at 200% text size, and the phone drawer no longer
  offers the desktop-only "collapse sidebar" control.
- The video player's controls use one neutral style in place of three unrelated colours, and its
  playback state chip is no longer amber.
- The shared kit gains `focus-ring-on-dark`, `btn-on-dark`, `input-on-dark`, `photo-chip`,
  `switch-track` and `switch-thumb`; the rules are in
  [the UI standard](docs/standards/ui-ux.md#kit-rules-that-keep-aa-true). The Chromium suite now
  runs axe-core over the main routes with data on them in both themes and fails on any serious or
  critical violation.
