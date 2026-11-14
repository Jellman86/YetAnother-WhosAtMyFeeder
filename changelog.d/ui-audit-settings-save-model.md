- Settings now tells you exactly what is unsaved. The bar at the bottom counts the changes and
  names the tabs that hold them, each a link, and shows only while a saved value would really
  change: Integrations no longer claims unsaved changes the moment it opens, and the bar never
  covers the last setting on a phone or a wide screen. **Discard changes** puts every saved value
  back, stored secrets included, without a request. The button is now **Save changes**
  everywhere, and the AI tab's separate **Apply style** is gone: choosing a prompt style fills the
  templates and the one Save keeps them.
- Leaving Settings, going Back or reloading with unsaved changes now asks first, naming what would
  be lost. Moving between Settings tabs still keeps your edits without asking.
- A refused save now says so where it matters. Nothing is stored, each refused field is marked
  with the reason in plain words (for example "Enter 65535 or less."), and the bar lists the
  fields with a link to each. A server failure says nothing was saved and what to try, instead of
  "Internal Server Error". Each result is reported once, as a notification, rather than twice.
- `POST /api/settings` now reports an instance address without a scheme (previously `400`) and
  turning on sign-in without a password as `422` validation errors that name their field, like
  every other refusal. See [the API reference](docs/api.md).
