- **Dismiss a warning on Health.** Each backend warning, earlier incident and open incident that comes
  from a recorded warning now has **Dismiss**. It hides that item for everyone on this install, and
  Health's counts and the sidebar's open-issue number leave it out. **Show N dismissed** lists what
  is hidden, each with **Restore**; nothing is deleted, and a diagnostics bundle still includes
  dismissed items, marked as dismissed.
  - A dismissed item comes back if it happens again: a dismissal covers one backend entry up to the
    newest occurrence you saw, and anything recorded after that shows it again.
  - The verdict still comes from the live checks. An incident a live check shows open now cannot be
    dismissed and says it clears by itself when the check passes.
  - **Clear error history** still removes everything, dismissals included
    ([docs/troubleshooting/diagnostics.md](docs/troubleshooting/diagnostics.md),
    [docs/api.md](docs/api.md)).
