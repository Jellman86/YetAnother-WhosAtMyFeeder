- **Scrollbars on a Mac behave like a Mac again.** YA-WAMF used to style its own scrollbars, which made
  Safari and Chrome on macOS show a permanent bar in every scrolling panel, and made the page move
  sideways when a dialog opened and took the bar away. The app now uses the system's scrollbars,
  which hide when idle and follow light and dark mode.
- The sidebar's System status no longer scrolls by a pixel or two at every window size. Its CPU and
  NPU line overhung its own line, so the card always had a little more to scroll to. On a short
  window, where the readings do have to scroll, they now end after the last whole line instead of
  showing the next line cut through its letters; the rest is still there to scroll to.
- A System status state that wraps, such as "Not connected", stays at the right edge with the others.
