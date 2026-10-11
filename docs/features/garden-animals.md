# Review garden animals

**Garden animals** is an owner-only review prototype in current `dev`. It collects
completed Frigate animal events separately from bird history. It does not yet
identify species or save model guesses automatically.

1. Open **Settings → Connection**, sync the camera list, and enable **Garden animals**
   for the camera you want to watch. Its **Feeder** or **Nest** bird role is independent.
2. Set **Frigate animal labels** to labels your detector actually tracks. The default
   is `cat, dog`. Adding `squirrel` here cannot make a detector learn squirrels;
   Frigate must already track that label and publish completed events over MQTT.
3. Save settings, then open **Garden animals** in the sidebar. Select **Needs review**,
   inspect the photograph, and choose **Confirm animal present** or **Dismiss capture**.
   **Return to review** restores a dismissed capture.

![Independent Garden animals toggle beside the bird camera role, with Frigate animal labels](../images/settings-garden-cameras.png)

![Owner-only Garden animals review with no captures and instructions to enable a camera](../images/garden-review.png)

Confirmation records animal presence, not the suggested species. Repeated MQTT
messages cannot create duplicate visits or undo your decision. Existing Frigate
history is not backfilled into this view.

Garden visits never enter bird totals, personalization, bird notifications,
BirdWeather, eBird or iNaturalist submissions. Bird labels, including custom bird
ingest labels, take precedence. People and vehicles cannot be configured as garden
labels. A later person or false-positive update removes the capture from all views
and prevents a delayed animal message from restoring it, even after capture is
switched off. This relies on Frigate's labels; a missed person could still be in
an animal photograph, so the view and its media are always owner-only.

Photographs are requested from Frigate only when viewed; this prototype does not
archive garden photographs or clips. They can expire before the review metadata.
An unavailable photograph disables confirmation. Review metadata follows
**Settings → Data → Detection Retention** when automatic cleanup is enabled;
turning off Garden animals stops collection but preserves existing reviews.

Automatic species identification still needs reviewed daytime and infrared animal
captures and hard negatives. The [developer replay](../development/garden-replay.md)
records the model checks and limitations tracked in
[#641](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/641).
