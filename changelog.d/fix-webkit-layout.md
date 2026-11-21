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
- **Leaving YA-WAMF in Safari goes where you asked, on a Mac and on an iPhone.** Going to another
  address while a page was still loading made Safari stop that page's loading code with the same
  message an out-of-date app gives, so YA-WAMF reloaded itself and cancelled the navigation. Before
  reloading for a page that failed to load, YA-WAMF now asks the server which version it runs, and
  reloads only when the server runs a different one. This does not depend on timing or on Safari saying
  the page is being left, which Safari on iPhone does not. On the same version nothing reloads, and the
  page keeps its **Try opening again** button. If the server cannot be reached, YA-WAMF does not reload
  and shows its "Refresh the page" message. A tab's one automatic reload is used only when a reload
  actually happens. The failed load is still written to the log.
