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
   **Return to review** restores a dismissed capture while its photo remains available.

![Independent Garden animals toggle beside the bird camera role, with Frigate animal labels](../images/settings-garden-cameras.png)

![Owner-only Garden animals review with model download, country filtering and camera setup instructions](../images/garden-review.png)

The first confirmation records animal presence. Species identification has a separate review. Repeated MQTT
messages cannot create duplicate visits or undo your decision. Existing Frigate
history is not backfilled into this view.

Garden visits never enter bird totals, personalization, bird notifications,
BirdWeather, eBird or iNaturalist submissions. Bird labels, including custom bird
ingest labels, take precedence. People and vehicles cannot be configured as garden
labels. A later person or false-positive update removes its Frigate event capture from all views
and prevents a delayed animal message from restoring it, even after capture is
switched off. This relies on Frigate's labels; a missed person could still be in
an animal photograph, so the view and its media are always owner-only.

Frigate events without an advertised snapshot are skipped. **Needs review** omits
captures whose photo is known to be unavailable, without deleting or changing
their review metadata. Confirmed history remains visible after photo loss.
Frigate event photographs are requested only when viewed and can expire before
their metadata. A failed download disables confirmation but does not discard the
capture: a network error is not proof that the photo is gone. Review metadata follows
**Settings → Data → Detection Retention** when automatic cleanup is enabled;
turning off Garden animals stops collection but preserves existing reviews.

## Collect candidates from motion recordings

If Frigate does not track the animals you want, optionally enable **Collect motion review
photos** for that garden camera in **Settings → Connection**, then save. Open **Garden
animals → Motion collection** and **Download Cedar detector (101 MB)**. This separate
MegaDetector v1000 Cedar model uses the species catalogue for its three outputs;
it needs no labels file.
It does not replace Frigate's bird detector or change bird classification settings.

Collection is off by default. One worker drains up to 24 queued recording windows
per camera, oldest first, taking turns between enabled cameras. Each window covers
up to ten seconds and samples three frames. Scan starts are at least ten seconds
apart, including processing time in that interval. Long scans finish and leave at
least one second of rest before another starts; failed scans retry thirty seconds
after failure. Queues refill from
Frigate metadata and the saved completion cursor, so restarting does not replay
completed windows. Longer recordings resume from the cursor instead of losing
their remaining footage. Overlapping recording metadata is merged before sampling.
No new database queue or retained clips are needed.

Only completed motion recordings from the last thirty minutes are considered.
Frigate must retain that footage. Pressure or repeated failures can let older
windows fall outside this catch-up limit without being scanned. This samples
activity; it does not track animals or promise to find every visit. Even within
a scanned window, a brief visit can fall between the three sampled frames.

Frigate can include keyframe padding in the returned clip. Up to five extra seconds
are tolerated, but samples stay within the requested duration. Recording windows
and decoded frame offsets are retained separately; displayed visit times are approximate.
The panel reports waiting, failures, the last attempted scan and the latest checked
camera's remaining queue count and check time. A full queue can have further footage
waiting in Frigate. Refresh the page to read the latest state.

In **Motion collection**, **Animal proposal threshold** adjusts Cedar's minimum animal
score for new motion photos (0.5 by default, configurable from 0.5 to 0.95).
A higher threshold reduces proposals but can miss small, distant or infrared animals;
it cannot eliminate confident errors such as feeders and toys. **Save animal threshold**
does not reclassify existing photos or change bird thresholds or the person privacy veto.
Each new motion photo records the threshold used with its source evidence.

Cedar runs on CPU with two inference threads and one video-decoding thread. It
yields to queued or running bird inference and stops if active Frigate cameras
fall behind. One garden operation runs at a time, with a 45-second motion-worker
deadline. Busy systems may collect no photos until pressure clears.

Candidates appear in **Needs review**, labelled **Candidate from retained motion
footage**. Each motion photo outlines the saved Cedar candidate before presence
confirmation. The box marks the detector's proposal; it is not an animal count or
proof that an animal is present. It stays visible if you dismiss a species suggestion.
Frigate event captures use their separate tracked-event path; a recorded SpeciesNet
crop is outlined after analysis when it matches the displayed photo dimensions.
The generic animal class includes birds, and toys or shadows can trigger
it. Confirm presence only after inspecting the photograph. A detected person in
any sampled frame rejects the recording. Known overlapping Frigate person events
also reject it, and later person updates erase overlapping motion evidence.
Person checks include the bounded padding around the requested recording window.
An unrelated false-positive bird, animal or vehicle event cannot erase an independent
motion review. Missing or overfull person history stops that scan. Recognition can miss
people; these photographs remain owner-only.

**Needs review** groups motion proposals around the same position on a camera into
one card, within a page of up to 128 captures. The group compares each box with the
first box, requiring at least 75% overlap by intersection over union and the same
detector. This is a review aid, not animal tracking: different visitors can occupy
the same position. **Previous photo** and **Next photo** show the original photos,
times and exact boxes; confirmation always applies only to the displayed photo.
Frigate events and confirmed/dismissed history remain individual captures.

Open **Review this group** to dismiss only the listed photos together after inspecting
them. Future captures, other camera regions and already-confirmed captures are
unaffected. **Undo group dismissal** restores still-available photos; changed reviews
or unavailable photos are skipped and counted. No photographs are deleted by grouping.
Dismissed motion photos can be reclaimed for new captures, so Undo is not permanent.

At most 128 motion photos of 512 KiB each are stored in the application database,
a 64 MiB photo budget. Clips are temporary and removed after each scan. Photos
expire three days after the recording; unconfirmed and dismissed motion captures
are then permanently removed. Confirmed history and identification metadata remain
subject to normal history retention. A recording cannot create another review or
undo a dismissal when the detector changes. Dismissed photos stay available for
**Return to review** until expiry or until a new candidate needs their space. At
the photo limit, the oldest dismissed photos are reclaimed first; pending and
confirmed photos are protected. A reclaimed capture stays in **Dismissed** until
expiry, with Restore unavailable and an explanation. If all photo slots belong to
pending or confirmed captures, collection waits for a dismissal or expiry.
Turning collection off does not immediately erase photos.

To request a species suggestion, open **Species suggestions** above the history:

1. Set a recognised country name or ISO code in **Settings → Location**. Filtering
   runs locally; coordinates are not sent to the model.
2. Choose and download a garden model, about **224 MB** per variant. The default
   **4.0.3b** uses the whole photograph with the model’s vertical border trim.
   **4.0.3a** requires Frigate’s tracked snapshot box or the retained motion detector
   box; it never guesses a crop.
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

If garden species data is unavailable, suggestions stay unavailable in this view.
Bird detection can still start and run. Restore the catalogue and restart the
application to restore garden suggestions.

Confirmation checks that Frigate still supplies the exact photo used by the model.
An expired or changed photograph cannot be used to confirm an old suggestion.
**Discard identification** revokes your identification confirmation without changing
animal presence. Dismissing animal presence also revokes its identification confirmation. No garden suggestions enable notifications or bird exports.

Automatic species identification still needs reviewed daytime and infrared animal
captures and hard negatives. The [developer replay](../development/garden-replay.md)
records the model checks and limitations tracked in
[#641](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/641).
