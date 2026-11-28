# BirdNET-Go Integration

YA-WAMF features deep integration with [BirdNET-Go](https://github.com/tphakala/birdnet-go) for audio-visual correlation. This allows the system to cross-reference what it sees with what it hears.

## How it works
1. **BirdNET-Go** identifies a bird song and publishes the detection to MQTT.
2. **YA-WAMF** stores these audio detections in its recent in-memory correlation buffer and persists them to the audio detection history.
3. When **Frigate** detects a bird visually, YA-WAMF checks its buffer inside the configured
   audio-correlation window (five minutes by default), looking for the visual species before
   treating a stronger different call as nearby context.
4. If a match is found, the detection is shown with an **Audio confirmed** badge. This is corroborating audio evidence, not proof that the species identification is correct.

Every persisted audio detection is browsable in its own right under **Audio history**, reached from
the sidebar under **Observe** or from **Open audio history** on the dashboard's **Heard** card. Calls heard but never matched to
a camera visit still live here, which is usually the fastest way to tell "the microphone heard
nothing" apart from "the correlation window missed it":

![Audio History: counts for detections heard, audio-derived species, peak hour and number of sources, above filters for window, species, source and minimum confidence, and a detection history table pairing each spectrogram with its species, time, source and confidence](../images/audio-history.png)

Below the log, **Analytics** shows calls heard over time, calls heard by weekday and hour in your
own time zone (the Leaderboard's activity grid, counting calls rather than captures), and the
species composition. Every figure follows the window chosen at the top of the page and the applied
filters, so the grid's total always matches **Calls heard**. Above the grid, as on the Leaderboard, a
row of chips (**All species** and the five species heard most in the window) shows when one species
calls. The row is hidden while the page is filtered to a species, because the grid already follows
that search.

## Setup

### 1. MQTT Topic
In **Settings → Integrations → BirdNET-Go**, make sure **MQTT topic** matches your BirdNET-Go configuration.
- **Modern BirdNET-Go:** Use the base topic (e.g., `birdnet`).
- **Legacy / Custom:** Use the specific text topic (e.g., `birdnet/text`).

> ℹ️ **Note:** YA-WAMF automatically reconnects if you change the topic or enable/disable BirdNET
> in the UI. When disabled, YA-WAMF does not subscribe to the BirdNET topic and does not ingest its
> messages.

### 2. The two URLs

**Settings → Integrations → BirdNET-Go** asks for two addresses, and they do different jobs:

| Field | Who uses it | Example |
|---|---|---|
| **BirdNET-Go internal URL** | The YA-WAMF backend, to fetch spectrogram images and audio clips. | `http://birdnet-go:8080` |
| **BirdNET-Go browser URL** | Your browser, for the dashboard links that open BirdNET-Go itself. Falls back to the internal URL when empty. | `https://birdnet.example.com` |

**If spectrograms do not load** but the links work, the internal URL is wrong or unreachable from
the container. **If the links go nowhere** but spectrograms are fine, the browser URL is wrong.

### 3. Sensor Mapping
For correlation to work, YA-WAMF needs to know which audio sensor belongs to which camera.
1. Go to **Settings → Integrations → BirdNET-Go → Audio buffer & sensor mapping**.
2. Check **Recently detected BirdNET sources** after audio messages have arrived.
3. Under **BirdNET source mapping (Optional)**, use **Add detected source…** for the corresponding camera, or type the stable source name.
4. Multiple source names can be mapped to a camera; comma-separated entries are accepted. Choose Save changes to keep the mapping.

A named camera without a mapping does not receive audio from another source. Use `*` only when you
deliberately want any source to correlate with that camera; a blank or missing mapping is not a
wildcard.

For cameras with microphones, BirdNET-Go supports multiple named RTSP audio sources. Enable audio
in each camera (AAC is the most interoperable choice), add and test each RTSP stream in BirdNET-Go,
and give it a stable name that matches the corresponding Frigate camera where practical. Map that
configured source name in YA-WAMF; current BirdNET-Go releases publish a stable `sourceName` as well
as the runtime `sourceId`. This is easier to maintain than copying a generated hash and lets every
camera contribute independent audio context. See BirdNET-Go's
[RTSP/multiple-source guide](https://github.com/tphakala/birdnet-go/wiki/BirdNET%E2%80%90Go-Guide#live-audio-streaming).

#### Renaming a source in BirdNET-Go

BirdNET-Go gives every source an id made from a hash of its connection string, and sends it with
each call as `sourceId`: the stream address for a network stream (`rtsp_3af0d74c`; also `http_`,
`hls_`, `rtmp_` and `udp_`), the device name for a sound card (`audio_card_22a9b331`) or a file
(`file_`). Its detection messages also carry the install's node name as `SourceNode` (Settings, Main,
Name in BirdNET-Go, `BirdNET-Go` unless you changed it). YA-WAMF identifies a source by that id on
that install, not by its name. Both are compared exactly as sent, case included, once spaces and
line breaks at either end are trimmed: `Shed` and `shed` are two installs.

- **One id is one source per install.** The hash covers only the connection string, so two installs
  that each read their own `rtsp://localhost:8554/audio`, or their own `default` sound card, send
  the same id for two different microphones. Give each install its own node name in BirdNET-Go so
  YA-WAMF can keep them apart.
- **A call that names no install** (an older BirdNET-Go, or a message without `SourceNode`) is kept
  apart from every install's sources, and also by its name, because two unknown installs can send
  the same id. YA-WAMF cannot follow a rename of such a source, or tell two unknown installs apart
  when their sources share both id and name: nothing in the message connects them.
- **A source's name** is the one BirdNET-Go sent, even when that is its id. When BirdNET-Go sent no
  name, the source is shown by its id.

So:

- **Renaming a source keeps one source in Audio history.** Its **Sources** list shows the source
  once, under its newest name, with all of its calls, and the source filter finds its whole history
  by its old name, its new name or its id. Each call in the list of calls keeps the name it arrived
  with.
- **A camera mapping still matches names and ids literally.** A camera mapped by a source's old
  name does not hear the source under its new name: after renaming a source in BirdNET-Go, update
  the camera's mapping under **Settings → Integrations → BirdNET-Go → Audio buffer & sensor
  mapping**, as before. Following a rename in camera mappings is planned as a follow-up.
- **Mapping a camera by the source's id survives a rename,** with three limits:
  - it only works for a source whose calls carry `sourceId`;
  - calls from before BirdNET-Go sent ids are not matched by the id, so keep their name in the
    mapping too (for example `rtsp_3af0d74c, birdcam`);
  - **Add detected source…** inserts the source's name, so type the id into the mapping yourself.

  A mapping by id also hears every install that sends the same id, as it always has.
- **Changing a source's address makes a new source.** A new RTSP URL hashes to a new id in
  BirdNET-Go, so YA-WAMF lists it separately, even under the same name. When two sources share a
  name, the **Sources** list shows each one's BirdNET-Go id, and its install when that is what
  tells them apart.
- **Calls from before BirdNET-Go sent ids** carry only a name. They join the source that carried
  the same name later, as long as only one source ever did (on the same install, when the call names
  one), counting calls you have hidden: hiding a call never moves an older call to another
  microphone. If two sources have carried that name, the older calls stay a separate entry, marked as
  calls without a usable BirdNET-Go id, rather than being credited to the wrong stream.
- **Guests** see only what the shared history holds: a source is named, filtered and counted from
  the calls inside the window you share, never from an older name.

Tracking sources changes nothing about how YA-WAMF recognises a call BirdNET-Go delivers again:
it still knows one by its source name and BirdNET-Go's detection number, as before. Two installs
whose sources share a name and send the same detection number therefore still count as one call,
as they did before this change.

YA-WAMF keeps at most 200 characters of a node name, source id or source name. A longer id, or one
with control characters, spaces inside it, `,`, `;`, `|` or `*`, is not used rather than shortened,
so two ids are never cut into one. A call whose id is not used is not one from before ids, so its
name is not used to join it to a source either: it is listed as an unknown source on its own
install, never under another install's source.

The upgrade that adds source tracking reads every stored call's payload once and records its
source. A call whose payload names no source, such as one from a BirdNET-Go version that sent
neither a source name nor an id, is listed as an unknown source, and its payload is not read again.
If you go back to an older release for a while, the calls it stores are read the same way the next
time this release starts, in small batches in the background.

### 4. Dynamic Sensor IDs (Wildcard)
If your audio source (like a re-streaming camera) generates a new Sensor ID every time it restarts, you can use a **wildcard** to allow any source for that camera. The species and time-window checks still apply.

- In the source mapping field for that camera, enter: `*`
- This tells YA-WAMF: "Ignore the source-name restriction, while keeping the species and configured time-window checks."

Keep host clocks synchronized and ensure timestamp payloads include the correct offset. Correlation uses UTC instants; matching display timezones alone does not correct a wrong clock or an incorrectly labelled timestamp. `TZ` controls local display and scheduling; see [Getting Started](../setup/getting-started.md).

### 5. Test the complete path

Use **Test BirdNET-Go path** in the setup wizard, or **Test BirdNET-Go** under
**Settings → Integrations → BirdNET-Go**. The staged diagnostic checks, in order:

1. the BirdNET-Go URL currently shown in the form, when one is set;
2. an isolated publish through the configured MQTT broker; and
3. synchronous ingestion of a mock Blue Tit detection into the correlation buffer and database.

The diagnostic stops at the first failed stage. A green result therefore means that every
displayed stage actually completed; it does not merely mean a background task was queued.
The MQTT probe uses a separate short-lived client, so it does not interrupt live event ingestion.
If a saved password is left blank in Settings, the stored secret is reused without returning it
to the browser. After proving insert and delete access, YA-WAMF removes the synthetic database row
and buffer entry so a diagnostic can never appear in history or confirm a real visual detection.

## 🛠 Technical Details

YA-WAMF is compatible with multiple BirdNET message formats:
- **CamelCase (Original):** `comName`, `score`, `ts`
- **PascalCase (New BirdNET-Go):** `CommonName`, `Confidence`, with the source as `sourceId` and
  `sourceName` (older builds sent `Source -> id` and `Source -> displayName`, or `src` and `nm`)

The system ignores "Sound Level" messages (`birdnet/soundlevel`) and focuses only on valid species identifications.

### Filtering low-confidence detections
By default YA-WAMF stores every BirdNET-Go detection it receives. To drop noisy low-confidence detections at ingest, set `frigate.audio_min_confidence` (`0.0`–`1.0`) in `config/config.json` or through `PUT /api/settings` as `audio_min_confidence`. It has no Settings control or environment variable yet. Detections below the threshold are neither buffered for correlation nor written to history. The default `0.0` stores everything. BirdNET-Go also has its own confidence and dynamic-threshold controls upstream; this setting is an additional YA-WAMF-side floor.

## Audio history and visual matches

The dashboard's **Heard** card summarizes persisted calls for the selected day and opens
Audio history, which is also in the sidebar under **Observe** while BirdNET-Go is turned on. The [Explorer](../features/explorer.md) can also show heard-only call bouts:
turn **Heard calls** on in Explorer for that device. Repeated calls are grouped, and matched calls
can appear with the corresponding seen visit rather than as duplicate cards. Audio-only
calls do not become visual captures or inflate camera counts.

Audio History provides date-window, species, source, and confidence filters plus top-species,
source, and hourly summaries. Use it to inspect individual persisted messages and spectrograms.
The window is **Today** (from your local midnight to now), **Last 24 hours**, **Last 7 days**,
**Last 30 days** (the default), **Last 90 days** or **Last 365 days**. Today moves on to the new day
at midnight while the page stays open. Guests see only the history the owner shares, so when that
starts after their own midnight the page says from what time Today is shown.

Source summaries process stored messages in small batches to limit memory use while other
requests run. Summaries still cover the entire selected window, so a narrower date range reduces
the work required for a large history. Hiding or restoring an audio row is reflected on the next
summary request.

An audio-history row shows a visual-match icon only when YA-WAMF finds a completed, non-hidden,
automatic video classification with the same scientific name, inside the configured correlation
window, and on the camera associated with that BirdNET source. Manual tags are deliberately
excluded: the icon means the independent video classifier agreed with the audio evidence. The icon
opens that exact visual detection; guest users receive links only inside their configured public
event-history window.

Detection details also look up persisted BirdNET history when you open them. This catches audio
that reached YA-WAMF after the visual event's initial correlation attempt. A matching species is
labelled as confirmed with its confidence and available BirdNET-Go media when the correlation rules
agree, even if the original visual row predates the audio message. Other sounds inside the same
configured time and source window appear as nearby audio context instead.

YA-WAMF normalizes incoming BirdNET timestamps to UTC before storing them. This keeps correlation,
history filters, retention, and leaderboard windows correct when BirdNET-Go publishes local-offset
timestamps (including daylight-saving changes) while Frigate events are stored as UTC. Existing
audio history is normalized automatically during the database upgrade.

Modern BirdNET-Go payloads also include a stable detection ID. YA-WAMF combines that ID with the
normalized source name before writing history, so an MQTT redelivery does not create a second row
or a second live-correlation observation. Different detections are never coalesced: the audio lane
processes them in broker order and remains independent of slower visual inference. Legacy payloads
without a stable numeric ID are still accepted, but cannot receive this source-level deduplication.

## Remove an incorrect audio detection

In Audio history, owners can choose **Hide from YA-WAMF** beside a detection and **Undo** while
the page remains open. Undo restores recent calls to live correlation immediately; calls older
than the configured buffer window return to history only. Hiding excludes the entry from history, statistics and future live
correlation. It does not delete anything in BirdNET-Go or rewrite existing visual identifications.
BirdNET-Go deletions are not automatically synced; a missing clip alone is not evidence of deletion.

Hidden rows remain as local tombstones, including during retention cleanup, so an MQTT replay
cannot restore them. During a database outage new audio is not used for correlation because its
visibility cannot be checked. The owner API can restore a row later using its local history ID.
