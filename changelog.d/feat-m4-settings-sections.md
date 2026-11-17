- Settings is now organised by the task you came to do: six sections instead of twelve tabs.
  **Cameras & connection** holds Frigate, MQTT and the cameras to watch. **Identifying birds**
  holds detection, the models and their hardware, and Beta features. **Alerts** holds
  notifications. **Sharing & integrations** holds the other services, AI, sign-in, guest access
  and telemetry. **Storage & upkeep** holds what is kept, the configuration backup, the repair
  jobs and deleting history. **Display** holds appearance and accessibility. Every setting is
  still there, in the same card as before; the [configuration guide](docs/setup/configuration.md#where-did-it-go)
  has a map from each former tab to its section.
- Old Settings links and bookmarks keep working. An address such as `/settings/models` opens the
  section that now holds it, scrolled to that part, at its new address
  (`/settings/identification#models`). Moving from one part to another, with a link, Back or
  Forward, scrolls to that part each time, and a reload keeps it.
- Help text across the app that pointed at a Settings tab, such as "Settings → Models", now names
  the section that holds it, in every language.
- The unsaved-changes bar now names the section for a changed theme font, colour theme or
  Explorer layout. Before, those three changes were counted but no tab was named.
