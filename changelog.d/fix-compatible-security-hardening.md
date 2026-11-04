- Configuration saves and generated installation secrets use exclusive temporary files and
  owner-only POSIX permissions, preserving the previous file if a save fails.
- Changing owner credentials revokes existing login tokens, media cookies, stream tickets and
  live streams after the change is saved. Normal upgrades keep existing logins, and connected
  OAuth integrations and legacy API keys keep working.
- Integration API failures and SMTP/router logs redact configured credentials and credential
  URLs while preserving useful error reasons and existing HTTP statuses.
