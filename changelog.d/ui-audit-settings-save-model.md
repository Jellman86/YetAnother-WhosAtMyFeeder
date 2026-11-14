- Settings now tells you exactly what is unsaved. The bar at the bottom counts the changes and
  names the tabs that hold them, each a link, and shows only while a saved value would really
  change: Integrations no longer claims unsaved changes the moment it opens, and the bar never
  covers the last setting on a phone or a wide screen. **Discard changes** puts every saved value
  back, stored secrets included, without a request. A stored secret's field shows it is stored
  again if you type in it and clear it, since saving an empty field keeps it. The button is now **Save changes**
  everywhere, and the AI tab's separate **Apply style** is gone: choosing a prompt style fills the
  templates and the one Save keeps them.
- Choosing another page with unsaved Settings changes now asks first, naming what would be lost,
  and reloading or closing the tab asks too. Back and Forward are never held up: your unsaved
  changes wait for you, and coming back to Settings puts them back with "You left with unsaved
  changes. They're still here." Passwords and keys are never kept outside the form, so the line
  names any you need to type again. Save or Discard clears them. Moving between Settings tabs still
  keeps your edits without asking.
- Kept Settings changes never outlive your session: signing out, an expired session or signing in
  again drops them at once, even when you sign out from Settings itself. They are tied to the
  session without copying its sign-in token, so no credential is ever kept with them. Coming back reads the saved values
  afresh, so a setting someone changed elsewhere meanwhile shows its new value. If you had changed
  the same setting, neither value wins silently: the field says the saved value changed elsewhere,
  the bar names it with **Use the saved value** and **Use my change**, and Save waits until you
  choose.
- A refused save now says so where it matters. Nothing is stored, each refused field is marked
  with the reason in plain words (for example "Enter 65535 or less."), the first one is opened and
  focused even on another tab, and the bar lists the fields with a link to each. A server failure says nothing was saved and what to try, instead of
  "Internal Server Error". Each result is reported once, as a notification, rather than twice.
- `POST /api/settings` now reports an instance address without a scheme (previously `400`) and
  turning on sign-in without a password as `422` validation errors that name their field, like
  every other refusal. See [the API reference](docs/api.md).
