- **Bird and Garden Discord and Pushover alerts now go through shared senders.** They read as
  before. Bird Discord embeds keep their bold detection line, teal colour and snapshot; Garden
  embeds keep their own footer. Both now treat names and cameras as plain text, so an underscore
  or bracket in a camera name can no longer turn into Discord formatting, never ping anyone, and
  wait for Discord to confirm the message. A Pushover alert counts as sent only when Pushover
  accepts it, and Garden alerts now carry the sighting time as the Pushover message time. A
  failure records only its type and status; verbose connection logs now hide a configured
  Discord webhook on any host, not only discord.com.
