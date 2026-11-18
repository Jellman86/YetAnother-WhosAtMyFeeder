- Fixed: a notification channel's test said "Passed" when nothing was delivered. A Discord webhook
  on an address that does not answer, a refused Pushover key or a Telegram chat that does not
  exist all read "Test notification sent". The test now passes only when the channel accepted the
  message. Otherwise the step fails and says why and what to do next, for example "Discord did
  not answer. Check the webhook address, then test again.", in your language and without ever
  showing the webhook address or a token.
- A test email that the mail server did not accept now says what to check (the SMTP host, port,
  user name and password, or to reconnect Gmail or Outlook) instead of "Failed to send test
  email".
