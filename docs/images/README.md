# Documentation screenshots

These screenshots illustrate the current UI with controlled example data. They
are documentation figures, not evidence of classification accuracy or a live
server's current health. All 18 earlier figures were refreshed on 11 October
2026 against the UI at `438ed1a`, and eight focused figures were added.

The capture uses the actual Svelte pages and components. HTTP responses are
provided locally at the API boundary; no settings are saved, models evaluated,
or production services contacted. The welcome and account screenshots use
first-run state only inside the local fixture. The DINO wizard screenshot uses
the normal re-run flow, with both location fields blank.

## Reproduce the capture

From the repository root, install the UI dependencies and Chromium once:

```bash
npm --prefix apps/ui ci
cd apps/ui && npx playwright install chromium && cd ../..
```

Start the current UI in one terminal:

```bash
APP_BRANCH=stable npm --prefix apps/ui run dev -- --host 127.0.0.1 --port 4189 --strictPort
```

In another terminal, from the repository root:

```bash
node scripts/capture_docs_screenshots.mjs
# Capture only the garden prototype controls and empty review view:
node scripts/capture_docs_screenshots.mjs --garden-only
```

Port 4189 keeps this capture separate from the browser regression suite. For
matching frontend and fixture version metadata, use the `stable` branch label
shown above; the fixture reads the version from `VERSION`. For
another local port, set `DOCS_UI_URL=http://127.0.0.1:PORT`. The capture script
rejects non-local UI URLs, URL credentials, queries and fragments. A network
guard aborts every request to another origin; local API responses are mocked,
including session-cookie and stream-ticket acknowledgements. All other API writes
are rejected, so no session or application state is written to a server. The script reports
browser page errors and exits unsuccessfully
if any occur. It blocks external font requests and uses the system font fallback.
The example clock is fixed to 11 October 2026, with the Europe/London time zone.

The dashboard overview uses the complete application shell, including the expanded
desktop sidebar and mobile navigation bar. The capture rejects a missing or clipped
desktop sidebar. Its live stream is an empty local fixture, so no live connection
is implied. The isolated [documentation page fixture](../../apps/ui/browser-tests/documentation.ts)
mounts the real Dashboard for focused figures and the Add observation page.
Other captures reuse the existing Settings, wizard, Explorer, review, model-evaluation, audio and species
browser fixtures. The isolated fixtures bypass application background schedulers;
the full application overview's requests are all handled by the same local guard.

## Data and privacy

- Service names are generic Compose names such as `frigate`, `mqtt` and
  `birdnet-go`. The account name is the example `admin`; passwords stay blank or
  redacted. No real credentials or feeder coordinates appear.
- [Model metadata](../../scripts/fixtures/documentation-models.json) is a read-only
  snapshot of the public model catalogue fields on the capture date. It contains
  the DINO, RoPE 336 and MobileNet descriptions and artifact details used by the UI.
- Runtime state, history counts, audio calls and health are representative fixture
  responses. The `example-compatibility` result illustrates the compatibility-only
  report format for one classifier; it is not the owner's complete evaluation.
  Its example NPU median is 120.4 ms. Accuracy was not measured by this figure.
- The feeder photographs in `fixtures/` are the project owner's Dunnock and
  European Robin images, supplied for this project's model work.
  They contain no location metadata in these copies. They are reused as recognition
  images in the example history; the example timestamps and counts do not describe
  the original captures. No third-party stock photographs are used.
- Screenshots are captured directly from the rendered UI, with focused element or
  viewport framing. They are not pixel-edited or assembled into a simulated UI.

## Figure coverage

Use alt text that describes what a reader can learn from each figure. Do not copy
example counts or runtime values into product guarantees.

| File | Visible information |
|---|---|
| `dashboard.png` | Complete desktop sidebar, Last 24 hours, visit field log, review queue and feeder context |
| `dashboard-mobile.png` | Mobile navigation bar with the same dashboard and review flow |
| `dashboard-field-log.png` | Dunnock visit, three captures, confidence and open action |
| `explorer.png` | Visit cards, filter rail and Heard calls between camera visits |
| `explorer-heard-calls.png` | Three Robin calls in a separate heard-between-visits card |
| `explorer-captures.png` | Native capture popover for a three-capture Dunnock visit |
| `leaderboard.png` | Monthly visit photographs, species shares, rankings and activity |
| `audio-history.png` | Listening history, source/confidence filters and audio analytics |
| `detection-detail.png` | Dunnock photograph, identification and record controls |
| `detection-photo-review.png` | Review sheet with photograph choices and feeder species |
| `add-observation.png` | Upload, Analyse, Review and Save flow before anything is added |
| `settings-garden-cameras.png` | Independent animal capture opt-in alongside the bird role |
| `garden-review.png` | Owner review prototype, separate views and first-capture guidance |
| `settings-map.png` | Grouped Settings navigation and setup-wizard entry point |
| `settings-connection.png` | Frigate, MQTT and selected camera controls |
| `settings-detection.png` | Saved Intel NPU preference and actual worker runtime status |
| `model-manager-dino.png` | Selected DINO model, memory estimate and location guidance |
| `settings-integrations.png` | BirdNET-Go and optional integration controls |
| `settings-notifications.png` | Global notification filters and channel controls |
| `settings-security.png` | Authentication and public-access controls |
| `settings-data.png` | History retention and separate photo/video storage limits |
| `settings-media-retention.png` | Always-kept photos/video and optional storage limits |
| `settings-health.png` | System status and recorded visits in the What happened timeline |
| `support-bundle.png` | Fresh diagnostics capture, issue notes and download controls |
| `model-evaluation-compatibility.png` | Compatibility-only result, provider median and actual artifacts |
| `setup-wizard.png` | First-run welcome and setup stages |
| `setup-wizard-account.png` | Admin account, password rules and authentication choice |
| `setup-wizard-dino.png` | DINO provider selection and blank paired feeder coordinates |

After recapturing, visually inspect every changed PNG, check the privacy boundary
above, and run the [documentation validation checklist](../documentation-standard.md#validation-checklist).
