# Review garden animals

**Garden animals** is an owner-only review prototype in current `dev`. It collects
completed Frigate animal events separately from bird history. It offers optional, owner-requested SpeciesNet suggestions. It never saves a model
guess as a confirmed identification automatically.

1. Open **Settings → Connection**, sync the camera list, and enable **Garden animals**
   for the camera you want to watch. Its **Feeder** or **Nest** bird role is independent.
2. Set **Frigate animal labels** to labels your detector actually tracks. The default
   is `cat, dog`. Adding `squirrel` here cannot make a detector learn squirrels;
   Frigate must already track that label and publish completed events over MQTT.
3. Save settings, then open **Garden animals** in the sidebar. Select **Needs review**,
   inspect the photograph, and choose **Confirm animal present** or **Dismiss capture**.
   **Return to review** restores a dismissed capture.

![Independent Garden animals toggle beside the bird camera role, with Frigate animal labels](../images/settings-garden-cameras.png)

![Owner-only Garden animals review with model download, country filtering and camera setup instructions](../images/garden-review.png)

The first confirmation records animal presence. Species identification has a separate review. Repeated MQTT
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

To request a species suggestion, open **Species suggestions** above the history:

1. Set a recognised country name or ISO code in **Settings → Location**. Filtering
   runs locally; coordinates are not sent to the model.
2. Choose and download a garden model, about **224 MB** per variant. The default
   **4.0.3b** uses the whole photograph with the model’s vertical border trim.
   **4.0.3a** requires Frigate’s tracked snapshot box; it never guesses a crop.
3. Choose a provider supported by your image and hardware. CPU, Intel CPU/GPU/NPU
   and NVIDIA GPU are supported runtimes; unavailable hardware produces an error
   rather than a CPU fallback.
4. Open **Confirmed animals**, inspect the photo and select **Suggest species**.
   Check the proposed identity, score and input context. Choose **Confirm
   identification**, **Dismiss suggestion**, or leave it unreviewed.

Bird inference has priority. If it is busy or begins while SpeciesNet is running,
the garden request stops and can be retried later. One garden operation runs at a
time, with a two-minute native deadline. Loading the model for each request costs
more time than a warm inference, but its process and memory are released afterward.

The catalogue holds both models’ ordered outputs, canonical identities, taxonomy
and country rules; there is no runtime labels file. Country filtering can broaden
the winning species to its family or higher group. It never substitutes a local
runner-up. An animal group is not a species identification; uncertain results stay
unidentified. A model score is not measured accuracy: a Patio toy car produced a
confident cattle prediction during testing. Review every suggestion. Recognised
people erase the capture and any saved suggestion; this cannot guarantee that a
missed person is absent from a photograph.

Confirmation checks that Frigate still supplies the exact photo used by the model.
An expired or changed photograph cannot be used to confirm an old suggestion.
**Discard identification** revokes your identification confirmation without changing
animal presence. Dismissing animal presence also revokes its identification confirmation. No garden suggestions enable notifications or bird exports.

Automatic species identification still needs reviewed daytime and infrared animal
captures and hard negatives. The [developer replay](../development/garden-replay.md)
records the model checks and limitations tracked in
[#641](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/641).
