- **Bird and Garden Telegram alerts now go through one shared Telegram sender.** Messages read
  exactly as before: bird alerts are the bold detection sentence after a bird, with a View
  detection button or the snapshot link, and Garden alerts are a bold title over the sighting.
  Both now escape, clip captions and attach photos the same way, turn off link previews with
  Telegram's current option, and count an alert as sent only when Telegram answers that it
  accepted it. A failure still records only its type and status, never the bot token. Garden
  alerts also stop borrowing the bird alerts' connection.
