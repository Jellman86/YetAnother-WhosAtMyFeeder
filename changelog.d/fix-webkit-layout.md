- **A new text size reaches every word in Safari straight away.** With Reduce Motion on (on the
  iPhone or in YA-WAMF's own Accessibility settings), choosing a larger or smaller size under
  **Appearance → Text size** left most of the page at the old size in Safari until it was reloaded:
  the sidebar, the status lines, the footer and the words inside cards and buttons. Reduce Motion now
  turns transitions off rather than making them very short, which is what kept Safari from passing
  the new size on.
- **The record's photograph fills its frame in Safari.** On a wide screen a short record showed its
  photograph narrowed, with a black band beside it, and the label naming a crop at the top of the
  frame sat on the crop's outline instead of under it.
- **Notification rows keep their words inside the row at a large text size.** A long word in a
  message, and a stopped job's "41 / 120" and "stopped" labels, now break or wrap rather than
  running past the row's edge.
- **Leaving YA-WAMF in Safari goes where you asked.** Going to another address while a page was
  still loading made Safari end that page's loading code with the same words a stale app gives, so
  YA-WAMF reloaded itself and cancelled the navigation, and logged a load failure that never happened.
  A failure that arrives while the page is being left is now ignored, and a real stale-app reload
  waits a moment so a navigation already under way can finish first.
