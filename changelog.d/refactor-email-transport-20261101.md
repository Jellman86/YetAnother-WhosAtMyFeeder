- **Bird and Garden email alerts now go through one shared email sender.** Emails read as before:
  bird alerts keep their detection template and Garden alerts their own short layout, with the
  photo inline when there is one. The sender chooses the OAuth mailbox or SMTP the same way for
  both, and a failure records only its type, never the SMTP exchange. All four alert channels,
  Discord, Telegram, Pushover and email, now share one sender each between birds and Garden,
  while each keeps its own rules for when to send.
