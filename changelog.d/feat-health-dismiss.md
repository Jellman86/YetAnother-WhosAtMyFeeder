- **Dismiss a warning on Health.** Each backend warning, earlier incident and open incident that comes
  from a recorded warning now has **Dismiss**. It hides that item for everyone on this install, and
  Health's counts and the sidebar's open-issue number leave it out. **Show N dismissed** lists what
  is hidden, each with **Restore**; nothing is deleted, and a diagnostics bundle still includes
  dismissed items, marked as dismissed.
  - A dismissed item comes back if it happens again: a dismissal covers one backend entry up to the
    number of occurrences you saw, and any occurrence after those shows it again, whatever the
    clock says. If it happened again while the page was open, or had already left the history,
    the page says so instead of claiming it was dismissed.
  - The verdict still comes from the live checks. An incident a live check shows open now, or has
    no reading for yet, cannot be dismissed and says it clears by itself when the check passes.
  - Dismissals are kept in memory with the error history they hide, so a restart resets both.
  - **Clear error history** still removes everything, dismissals included
    ([docs/troubleshooting/diagnostics.md](docs/troubleshooting/diagnostics.md),
    [docs/api.md](docs/api.md)).
