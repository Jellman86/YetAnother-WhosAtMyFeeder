# YA-WAMF Roadmap

The single, forward-looking plan for YA-WAMF. This is where **planned** and
**in-progress** work lives; **completed** work moves to [`CHANGELOG.md`](CHANGELOG.md)
and is summarised in the [Delivered](#3-delivered) catalogue at the bottom.
Entries are ordered by product and safety dependency, not promised dates. Each
entry states an outcome and the evidence needed to call it complete; priority
and effort are planning aids, not release promises.

> **YA-WAMF is already feature-rich.** This roadmap tracks what's *next*, not what
> exists — see the [README](README.md) and [Delivered](#3-delivered) for current
> capabilities.

It is anchored by two honest assessments of *where we stand*:

- [Gold-Standard Review (2026-07-07)](docs/reviews/2026-07-07-project-quality-and-gold-standard-review.md) — quality assessment and the incremental path.
- [Telemetry Health Findings (2026-07-09)](docs/reviews/2026-07-09-telemetry-health-findings.md) — what actually fails across the fleet.
- [Image Classification Pipeline Review (2026-07-20)](docs/reviews/2026-07-20-image-classification-pipeline-review.md) — evidence provenance, temporal consensus, HQ media, and runtime recovery.
- [Detection Queue and Jobs Review (2026-07-22)](docs/reviews/2026-07-22-detection-queue-and-jobs-review.md) — bounded intake, restart recovery, lifecycle ordering, and owner-visible work.

---

## How to read this roadmap

- **Priority:** `P0` critical · `P1` high · `P2` nice-to-have · `P3` future.
- **Effort:** `XS` <1d · `S` 1-3d · `M` 4-7d · `L` 1-3wk · `XL` 3wk+.
- **Status markers:** ✅ done · 🔄 in progress · ☐ not started.
- **Release scope:** only work listed under [3.0 exit criteria](#30-exit-criteria) blocks the
  release. A priority describes value and sequencing, not whether an item blocks `3.0`.

**Issues first.** Before new feature work, clear anything in `ISSUES.md` and the
[GitHub issue tracker](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues).
If a section ever claims "none open", treat it as stale and check both sources.
Issues retain implementation-ready scope, acceptance criteria, and discussion;
short-lived pull requests deliver reviewable slices into `dev`. Code and tests
remain the source of truth, so roadmap work is not shipped until the repository
proves it.

---

## 1. The Road to 3.0

`3.0` is the next major version. It has a deliberately bounded set of exit criteria; the
P2/P3 feature and platform backlog below does not delay the release unless an item is
explicitly promoted into those criteria. The release completes the defining product work,
proves the lossless migration path, and removes deprecated runtime paths.

The sub-sections are ordered as the program runs: **exit criteria → foundations already
delivered → release-defining initiatives → non-blocking backlog → breaking removals.**

### 3.0 exit criteria

`3.0` can ship when all of the following are true:

- [ ] The UI simplification pass has made Settings and the primary owner/guest journeys coherent,
  responsive, keyboard-operable, and honest about loading, empty, error, and destructive states.
- [ ] The dedicated, versioned SQLite species catalogue is authoritative for model-output identity
  and translated species names; every supported model checksum has a complete output-index mapping,
  label text files are no longer runtime truth, and upgraded detections preserve their history and
  owner overrides.
- [ ] Native editorial review is complete for locales presented as fully supported, or any residual
  language-quality limitations are labelled honestly in the release notes.
- [x] Stable installation and recovery docs match the shipped Compose defaults and first-run auth
  state machine; all user-facing pages are reachable from the docs hub.
- [ ] The split-to-monolith migration is exercised against preserved `/config` and `/data` volumes
  and documented as lossless.
- [ ] The legacy split deployment and `X-API-Key` path are removed from the recommended/runtime
  surface, with migration guidance available before users update.
- [ ] The repository Definition of Done passes, and release notes state the removals, migration
  path, hardware limits, and any remaining translation limitations.

### 1.1 Engineering foundations — ✅ met

The engineering and fleet-health gates that had to land before `3.0`. Both are complete;
kept here for traceability.

#### Gold-Standard engineering gate 🏅
**Priority:** P0 | **Effort:** M | **Status:** ✅ Gate met

The gap between the `CLAUDE.md` contract and the codebase is closed to the point that the
release ships against the full bar. Tracked assessment:
[Gold-Standard Review](docs/reviews/2026-07-07-project-quality-and-gold-standard-review.md).

- ✅ **CI enforcement** — Ruff lint + format gates, backend coverage floor ratcheted 20%→60%
  (measured ~65%), and `CONTRIBUTING.md` rewritten against the contract.
- ✅ **API contract** — build-time OpenAPI artifact (`backend/openapi.json`) with a CI drift
  check, and a generated SPA type contract (`apps/ui/src/lib/api/generated/openapi.ts`) with a
  CI freshness check, so backend/frontend drift fails review.
- ✅ **Documentation governance** — documentation standard published, governance files added
  (`AGENTS.md`, `CODE_OF_CONDUCT.md`), local links/API routes checked in CI, and the stable-install
  plus authentication-recovery paths corrected against current behaviour.

The remaining generated-type adoption is a small, non-blocking carry-over — see
[Engineering carry-overs](#16-engineering-carry-overs).

#### Fleet health: Frigate media reliability + telemetry signal 🩹
**Priority:** P1 | **Effort:** M | **Status:** ✅ Complete

All four recommendations from the
[Telemetry Health Findings](docs/reviews/2026-07-09-telemetry-health-findings.md) shipped:

- ✅ **Recording-frame classification fallback** — when snapshot, thumbnail, and cached image
  all fail, a frame is extracted from Frigate's continuous recording at the detection moment and
  classified, instead of dropping the detection (the fleet's most common real failure).
- ✅ **In-app Event-Not-Found guidance** — the Errors page surfaces the tuning guide as a calm
  advisory when the media-unavailability drop rate is genuinely elevated.
- ✅ **Cleaner telemetry signal** — expected `filter_*` drops are informational and excluded
  from health reporting; critical stage failures now carry `error_type` + `stage` context.
- ✅ **Old-build critical retired** — the `classify_snapshot` critical is confirmed
  `2.9.15`/`2.10.0`-only (resolved on `2.11`+); stale installs are nudged by the in-app update prompt.

### 1.2 Required product work

The headline work that makes `3.0` a major version: a guided first run, a cleaner product
surface, a codebase reviewed to the gold standard, and complete translations.

#### Versioned species catalogue and model-output identity 🗂️
**Priority:** P1 | **Effort:** XL | **Status:** 🔄 Phases 0, 1, 3 and 4 delivered; Phase 2 advisory-only by design; Phase 5 mostly delivered

Design: [`docs/plans/2026-08-12-versioned-species-catalogue-design.md`](docs/plans/2026-08-12-versioned-species-catalogue-design.md).
What is already built, what it is worth and what has to be reworked:
[`docs/plans/2026-08-19-species-catalogue-reconciliation.md`](docs/plans/2026-08-19-species-catalogue-reconciliation.md).
Source measurements: [`docs/plans/2026-08-19-species-reference-source-decision.md`](docs/plans/2026-08-19-species-reference-source-decision.md).

Make a dedicated `/data/species_catalog.db` authoritative for species identity instead of relying on
raw model-label text and whichever name a provider returned at detection time. It stays separate
from the detections database so the catalogue can be enriched, versioned, validated and rolled back
without rewriting detection history. It holds the complete taxon set emitted by supported models,
accepted scientific names, source identifiers, synonyms, RFC 5646 translated common names,
provenance, and owner overrides. Every exact model artifact checksum and output index maps to a
canonical YA-WAMF species identity or an explicit non-species class.

This does not pretend classifiers can work without an ordered output mapping. It replaces standalone
label files as runtime truth with a checksum-bound mapping imported into SQLite.

##### Delivered so far

A seed catalogue built from the IOC World Bird List (11,276 species, 87,656 localized names,
CC BY 3.0, reproducible build, digest-verified at runtime), the source measurements behind choosing
it, label-file verification against the registry checksum with the verdict surfaced on the Health
page, and a first output-index mapping.

##### The defect that shaped the design, and its fix

The first delivered layer keyed identity on the **scientific name**. Those change when taxa are
split, lumped or synonymised, so `Parus caeruleus` and `Cyanistes caeruleus` became two different
birds to anything keying on the text, and history divided silently. The opaque `species_id` is the
fix and it has landed: aggregation, filtering, audio, and the daily rollup all group on it, and the
catalogue records resolved synonyms so a renamed taxon stays one bird
([#272](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/272), closed). The live proof
was a jackdaw split into `Coloeus monedula` (102 rows) and `Corvus monedula` (28) on a real install;
after the synonym import it is one species with 130.

New consumers should key on `species_id`, never on label or name text.

##### Phases

| Phase | State |
| --- | --- |
| 0. Freeze the contract and provenance gate | ✅ delivered ([freeze note](docs/plans/2026-08-19-species-catalogue-phase0-freeze.md)): pinned sources (IOC 14.2, CoL COL26.7 by DOI and export digest, eBird 2025) in a machine-checked manifest with a licence/redistribution gate; per-artifact label grammar declared in the registry; 100%-coverage artifact [inventory](docs/reviews/2026-08-19-species-catalogue-phase0-inventory.md) held current by a regression test; and the [non-bird mapping report](docs/reviews/2026-08-20-col-nonbird-mapping-report.md) (exact/synonym/lump/unresolved, nothing guessed). Bird-side split/lump analysis rides with the Phase 2/3 eBird crosswalk |
| 1. Catalogue schema and deterministic builder | ✅ delivered: the dedicated Alembic stream, full catalogue schema, deterministic seed build from IOC plus the 7,865 Catalogue of Life non-bird taxa, marker-guarded seed-then-copy into `/data`, and the transactional release importer with rollback (single-head, reversible, CI-smoked, constraints in-schema; interrupted imports leave the previous release active; identities are never deleted; a lost catalogue is reported, never silently replaced) |
| 2. Checksum-bound model mappings | 🔄 the compiled mappings and the diagnostics are delivered: every supported classifier artifact is registered in the catalogue by its model checksum, with 21,973 of 23,332 output indices resolved to canonical identities, declared `background`/`unknown` class kinds, and 1,359 unresolved indices left as visible gaps ([coverage report](docs/reviews/2026-08-20-model-output-mapping-coverage.md)); the Health page reports the active release, coverage, and gaps in plain words, and the activation check (checksum resolved against SQLite, tensor width verified, unregistered/incomplete/width-mismatch verdicts) exists and is tested. Remaining: flipping that check from advisory to enforced at model selection, which lands with Phase 5's retirement of label-file authority so gap-bearing supported models are not broken in the meantime |
| 3. Shadow resolution and historical backfill | ✅ delivered: live shadow resolution — detections gain nullable `species_id` / `model_artifact_id` / `model_output_index` columns by reversible migration, every live classification resolves its checksum-bound output through the catalogue beside the label path, identity persists only on agreement (recorded synonyms count), and disagreements are counted in Health shadow statistics rather than written to history. The conservative historical backfill is delivered (rows whose scientific name resolves to exactly one identity gain `species_id` at startup, idempotently, with ambiguous and unknown names counted and left untouched), and the identity-writing pipelines are wired: backfill imports resolve through the shared save path, video refinements shadow-resolve with a guard against attributing a queued result to a since-swapped model, and manual observations attach canonical identity by the same unique-name rule with no artifact provenance, since a manual identity is human-asserted. Audio correlation writes no primary identity today; its canonical joins arrive with Phase 4 |
| 4. Make catalogue identity authoritative | ✅ delivered: species aggregation groups on the catalogue's opaque `species_id` with the taxon and name keys kept underneath, each source namespaced so an id from one database cannot collide with an id from the other, and filtering follows the same key so a merged species opens to every row the leaderboard counted. The leaderboard now returns the key it grouped on, so trend lookups join on it rather than rebuilding the rule. Verified against real detections: the same 42 groups before and after, none split and none merged. Delivered since: one shared name-precedence function, so a group is named from its identity (owner rename, then the catalogue's curated name for the reader's language, then English, then the scientific name) rather than from whichever of its rows sorted last; measured on real data as 3 of 42 species moving to the IOC spelling, and it supplies the Italian and Chinese the previous sources lacked. Audio detections now carry the same identity, resolved at ingest by the same conservative rule and backfilled for existing rows (55,998 of 56,026 on a real install; the 28 that do not resolve are `Corvus monedula`, which IOC calls `Coloeus monedula`, and stay split until the catalogue records synonyms, see [#272](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/272)). `species_daily_rollup` is delivered: it persists its key and holds aggregate history whose detections no longer exist, so it gained `species_id` and a re-keying migration that refuses to collapse a key whose rows disagree on identity, guarded by a `COUNT(DISTINCT ...) = 1` check rather than a `MIN()` guess. Remaining: taxonomy provider sync as an explicit catalogue job |
| 5. Remove label-file authority before `3.0` | 🔄 mostly delivered: every model output now carries a catalogue row, including the ones nothing could name, so the label text no longer lives only in `labels.txt` ([#276](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/276)), and existing installs actually receive those rows rather than being skipped as already imported ([#278](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/278)). A registry model's labels are now read from the catalogue instead of its label file, used only for a complete contiguous set matching the declared output width, since a short mapping would truncate a model's classes and a gap would shift every later label onto the wrong class; verified on a live install as reproducing all ten installed label files byte for byte, 34,746 labels. The compatibility importer for owner-supplied models is delivered: it derives a mapping from that model's own labels, records every output it cannot name, refuses an identity unless every reading of a label agrees, skips registry models so a derived mapping can never stand in for a reviewed one, and its labels are never served back as catalogue-verified. Measured against the reviewed mappings on four real label files: 11,509 outputs where both named a species, zero disagreements. Owner diagnostics now name every pinned source in the active release with its version, licence and citation, and state in plain words that the catalogue is a separate file from detection history, that rolling one back changes names and never recorded sightings, and that a backup of the data directory covers both; documented under Taxonomy & Naming. The dead name-keyed rollup reader that predated identity-based aggregation is gone. Owner renames, the one piece of naming an owner authored, now live in the catalogue keyed on the species rather than on a spelling of its scientific name, and existing ones are carried over on startup; the copy in the detection database is still written and read as the bounded pre-3.0 compatibility reader. Remaining: the name-recovery SQL that reads `taxonomy_cache` cannot simply retire, and the reason is measured rather than assumed. On a live install 710 of 763 visible detections carry a catalogue identity; of the 53 that do not, 49 are `Unknown Bird` with no scientific name to resolve and the remaining 4 are identifications coarser than a species (`Rattus`, `Gallus`, `Troglodytidae`). The catalogue holds species, so those can never resolve to one. That is a modelling difference, not a migration gap, and it needs a decision before `3.0`: either the catalogue gains higher-rank concepts (its `species.rank` column already allows for it, and the seed writes only `species`), or the compatibility reader stays for coarser-than-species outputs and stops being called temporary. `taxonomy_translations` is a provider cache of 169 rows in 4 languages against the catalogue's 87,656 curated names in 9, and folding provider names into a provenance-tracked table would cost the curation story more than it gains. After that decision: flip the Phase 2 activation check from advisory to enforced and stop shipping `labels.txt` |

##### Cheap, independent of the phases

- ✅ The Health page's Naming Sources card now explains its limits in words: whether a species
  catalogue exists, how many species it holds, and how many model output classes still have no
  catalogue identity and keep their label text.
- ✅ Measured: 84 of 707 European model labels (11.9%) resolve to no scientific name in the bundled
  IOC reference, dominated by stripped possessive apostrophes (`Audouins gull`) that a Phase 2
  apostrophe-insensitive alias rule should recover — see the
  [Phase 0 inventory](docs/reviews/2026-08-19-species-catalogue-phase0-inventory.md). No further
  source is warranted before that rule exists.

**3.0 gate:** all supported models and regional variants have complete mappings; normal inference
and reads work offline; locale changes affect display only; catalogue refresh is transactional and
reversible; backup/restore includes both databases; and real upgraded databases prove that
detections, unresolved legacy rows, provider identifiers, and manual names survive without
reinterpretation or loss.

#### First-run setup wizard 🧭
**Priority:** P1 | **Effort:** L | **Status:** ✅ Shipped on `dev` — multi-part, hardware-validating, re-runnable from the Settings navigation ([design](docs/plans/2026-07-12-first-run-setup-wizard-design.md))

A friendly, **skippable** guided setup that configures YA-WAMF end to end and — crucially —
is **idempotent and re-runnable at any time** from **Setup wizard** in the Settings navigation (running a step again is safe and
never clobbers unrelated config). Steps:

- **Model selection with on-hardware validation** — pick a classifier and confirm it actually
  loads and runs on the providers available to the running image. The shared provider sweep now
  intersects the image package, host probe, and selected model; tests ONNX CPU/CUDA and OpenVINO
  CPU/GPU/NPU as applicable; compares real-image output with a CPU baseline; and persists the
  measured provider order. A reviewed global candidate list can widen what the isolated sweep
  probes without making that provider globally selectable. Schema-4 evidence is bound to the
  runtime stack, visible hardware, image flavour, and model checksum, so stale proof fails closed.
  The wizard validates only the selected installed model, while the Diagnostics surface can
  optionally download and test the whole registry.
- **Integrations** — Frigate, BirdNET-Go, media servers, notifications: guided connect + test.
- **Frigate settings** — cameras, recording-retention guidance, and the detection gates that
  drive the Event-Not-Found problem (`min_score` / `min_initialized` / `threshold`).
- **Common quality configs** — HQ snapshots, crop selection, verification gates.
- **Optional retained-history import** — start a visible background classification job for bird
  events Frigate still retains without delaying the rest of setup. Existing enrichment is
  preserved and unavailable BirdNET-Go history is stated honestly.

Each step is independently re-runnable; skipping the wizard leaves the current config untouched.

The shipped hardening pass also closes the setup boundary end to end: enabling auth returns and
stores the initial owner session atomically; completed auth-disabled installs cannot be claimed
through the first-run endpoint; crop-detector artifacts are excluded and rejected as classifiers;
readiness checks enabled-integration credentials without pretending to be live health; staged
diagnostics test current form values and durable BirdNET ingestion; re-run sections return to the
review map; refresh/save failures have recovery UI; and the portalled wizard traps/restores focus,
supports scoped Escape, and bounds model-validation polling. Settings-backed steps now fail closed
until saved configuration loads successfully, authenticated MQTT is supported in the guided flow,
and the final review is localized from structured readiness codes.

#### UI simplification & polish ✨
**Priority:** P1 | **Effort:** L | **Status:** 🔄 In progress — Settings simplification and the
background-work surface complete; the remaining primary owner and guest journeys next
([design](docs/plans/2026-07-16-settings-navigation-simplification-design.md))

Make the whole UI clean, coherent, and calm — **especially Settings**, which is currently
bloated with indistinct sections. ✅ The research-and-codify step is done: the UI/UX standard
(Nielsen's heuristics, WCAG 2.2 AA, Refactoring UI craft) is codified in `CLAUDE.md` §5 and
[`docs/standards/ui-ux.md`](docs/standards/ui-ux.md). Remaining: apply it consistently across
the owner and guest surfaces (information architecture, grouping, progressive disclosure,
empty/error states) — the "full UI refresh" half of the major-version jump.

✅ **Settings pass:** task-based navigation, semantic camera controls, and progressive disclosure
now cover every Settings tab. Optional services are toggle-first, inactive credentials and tests stay
hidden, maintenance/analytics/destructive tools no longer compete with routine policy, nested card
noise and structural emoji are reduced, and the Settings type floor is 12px. The remaining work is
the primary owner/guest journey review, including their loading, empty, error, and destructive states.

✅ **Less-frequent owner journeys pass:** Model Evaluation now speaks the same visual language as
the rest of the app. It was the only page on Tailwind's `gray` ramp while every other page uses
`slate`, used Tailwind blue where the app's accent is `brand`, styled its controls as raw utility
classes rather than the kit in `app.css`, and had no control meeting the touch-target floor. Add
observation was checked against the Evidence page shape and already follows it: slim bar, the
1.35fr media and 0.85fr decision rail, and a confirm that names the bird it will add. Remaining on
this surface: Model Evaluation carries no translations at all, which is its own piece of work
rather than part of the visual pass.

✅ **Background work pass:** the separate jobs view is gone. It showed the same work three times
over, as four counters, a "Work Lanes" list and an "Active Work" list, with two lanes sharing the
title "Analyze Unknowns" and rows named after raw Frigate event ids. The notifications timeline
already carried every job with its live progress, so the second view mostly disagreed with the
first. Notifications is now the single surface for background work, and the one control the jobs
view held alone, resuming a queue the circuit breaker paused, sits at the top of it where work
needing a person belongs. Jobs are named by the work rather than the event, with the event kept as
detail so two clips analysed at once are still told apart. Remaining on this surface: the empty
state still describes only bird visits and does not yet mention the background work it now owns.

#### A public projection of the settings a viewer needs 👥
**Priority:** P1 | **Effort:** S

`/api/settings` is owner-only and returns everything, so the SPA has no way to read a single
display preference as a guest. Every setting that shapes what a visitor sees has therefore been
copied onto `/api/auth/status` one field at a time as somebody notices it is missing. That payload
now carries around twenty display preferences and is not really an auth endpoint any more, and the
pattern only finds a defect after a visitor has already been given the wrong interface.

Four were fixed this way in the 2.18.0 follow-up work: the Explorer layout, high contrast, the
dyslexia font, and reduce motion. A sweep of every `settingsStore.settings` read outside the
Settings page found three more still open, all on guest-visible surfaces:

- `classification_threshold`. `needsReview()` returns `false` when the threshold is null, so a
  guest never sees a row flagged as needing a person on confidence, on the Explorer list, the
  Dashboard field log, or a detection card. The layout standard states that flag as one of the
  three signals a visit carries, so the guest view is currently making a claim it cannot support.
- `ebird_default_days_back`. The nearby radius already travels publicly, so the window beside it
  reads "last 14 days" to a guest whatever the owner configured. Same defect the radius fix closed,
  one field along.
- `recording_clip_enabled` and `clips_enabled`. Both read false for a guest, so the play affordance
  is withheld independently of `public_access_allow_clip_downloads`, which is the setting that is
  supposed to decide it.

The outcome wanted is one small public projection of the settings a viewer legitimately needs,
served to guest and owner alike, so a new display preference is public or owner-only by decision
rather than by whether anyone remembered. Complete when the three above are served from it, the
auth status payload stops accreting display preferences, and a test asserts that a guest and an
owner resolve the same value for every setting in the projection.

✅ **Primary observation and history pass:** Dashboard, Leaderboard, Species details, BirdNET-Go
History, Explorer filters, detection tiles, and detection details now share the calmer first-run
visual language. Repeated cards have become divided information surfaces, media and rankings lead
their records, small-screen layouts avoid horizontal overflow, technical identifiers use progressive
disclosure, and interactive controls retain touch and keyboard affordances. Remaining work is the
same treatment across the less-frequent owner journeys plus a final cross-route loading, empty,
error, and destructive-state audit.

✅ **Cross-route loading and delivery pass:** Operational pages and language catalogs now load on
demand, the entry bundle is about 94% smaller, fingerprinted assets are compressed and
cached safely, and route-download failures recover in place. Quick navigation avoids loading-state
flicker; a quiet delayed status replaces page-sized skeleton walls on genuinely slow connections.
Long-lived authenticated tabs now replace stale live connections when identity changes, use one
adaptive analysis-status poller, pause routine polling while hidden, bound background requests with
timeouts, and load live camera frames only on demand. Explorer and Leaderboard loads now cancel or
ignore superseded responses, portrait enrichment has bounded concurrency and memory, shared
detection startup is single-flight, and full-visit checks no longer accumulate recurring timers or
unbounded per-event state while browsing history. Dashboard audio, Settings maintenance status, and
model-download status refreshes are also bounded against hidden tabs, stalled requests, overlapping
ticks, and navigation cleanup. Camera health now comes from one lightweight Frigate stats poll rather
than image success, while its looping viewer fetches only the selected camera and pauses when closed
or hidden.
The remaining audit is focused on page-owned empty, error, refresh, and destructive states.

✅ **Background-work and Jobs pass:** the Jobs workspace now uses a canonical owner-only server
snapshot for automatic video analysis, HQ snapshots, full-visit clips, and backfills instead of
depending only on browser-local progress. Queue depth, actual worker concurrency, waiting phases,
and blockers remain distinct; queued work is not counted as running. The global banner includes
only prominent owner-triggered work, while routine per-detection work remains available in Jobs.
The surface uses one divided information region, accessible progress semantics, translated status
copy, explicit retry feedback, and no control that merely hides server-owned active work. Historical
bird imports now use the same acceptance gate as live detections. Completed snapshots are fetched in
a deterministic full-frame representation and receive a locally restored, aligned Frigate crop before
that shared gate, while already-cropped and temporally unaligned inputs reject stale coordinates.

#### File-by-file code-quality review 🔬
**Priority:** P1 | **Effort:** XL | **Status:** ✅ Completed

✅ **Completed.** The code-quality standard for our stack
(Python/FastAPI + Svelte 5/TypeScript) is codified in `CLAUDE.md` §4 and
[`docs/standards/code-quality.md`](docs/standards/code-quality.md). The file-by-file review and
refactor is complete, with permanent frontend/backend source gates preventing the reviewed
contract, typing, layering, async-I/O, and hygiene failures from returning.

Completed review tranches:

- ✅ **Owner debug API** — extracted database diagnostics behind a repository, added explicit
  response models for every endpoint, made secret redaction independently testable and consistent
  with the application-wide `***REDACTED***` contract, and moved filesystem inspection off the
  async event loop.
- ✅ **Python formatting baseline** — brought the remaining backend files into the enforced Ruff
  format baseline so the repository-wide formatter check is clean before deeper review batches.
- ✅ **Frontend live-update boundary** — replaced `any` across the root SSE wiring and coordinator
  with explicit payload, health, notification, and translation contracts; normalized required
  detection fields at the untrusted JSON boundary and added regression coverage.
- ✅ **Frontend API and operational stores** — removed `any` from maintenance/system clients,
  detection state, health interpretation, incident state, diagnostics snapshots, and reclassify
  recovery; external payloads now enter as `unknown` and are narrowed before use.
- ✅ **Shared frontend components** — typed navigation, settings tabs, camera roles, health runtime
  state, event handlers, timers, translations, and notification error parsing across the reusable
  component layer.
- ✅ **Chart and map vendor boundaries** — replaced ApexCharts and Leaflet `any` usage with typed
  constructors, instances, DOM extensions, option records, maps, layers, and dynamic-import guards.
- ✅ **Events and health pages** — typed URL filter admission, naming inputs, operational health
  metrics, and user-facing error extraction across the Events and Health diagnostics surfaces.
- ✅ **Species analytics page** — typed leaderboard rows, weather buckets, comparison series, chart
  axes/tooltips/options, stable serialization, chart capture, and analysis errors end to end.
- ✅ **Audio and detection detail surfaces** — typed Audio History chart options and removed `any`
  from detection/species modals through shared naming inputs, API response fields, timers, and safe
  unknown-error extraction.
- ✅ **Settings and frontend type gate** — replaced Settings casts with domain normalizers, typed
  input attributes and timers, standardized unknown-error handling, and added a full-source Vitest
  gate that rejects explicit `any` in application TypeScript/Svelte outside generated contracts.
- ✅ **Backend endpoint contracts** — authentication, Settings, classifier, maintenance/status,
  Events, and model-evaluation JSON responses now publish explicit generated contracts; binary
  model-evaluation artifacts are explicitly classified as file responses.
- ✅ **Backend persistence boundaries** — all HTTP routers are free of direct database execution.
  Detection, OAuth-token, eBird-export, species taxonomy/cache/search, and video-share persistence
  are owned by focused repositories.
- ✅ **Classifier download I/O** — model-directory inspection, archive extraction, asset writes,
  and synchronous model reloads are dispatched off the async request loop.
- ✅ **Async blocking-I/O review** — database migration/backup work, uploaded and pipeline image
  decoding, video temp-file handling, media-cache cleanup, model-evaluation artifacts, model
  discovery/activation, and AI recording reads now run through async-native APIs or worker threads.
- ✅ **Backend architecture gates** — permanent AST-backed tests reject router-owned database
  execution, missing endpoint response contracts, incomplete repository signatures, direct blocking
  I/O inside async functions, untracked TODO/FIXME notes, and application `print()` calls.
- ✅ **Completion verification** — 1,390 backend tests pass (65 platform/model skips), backend
  coverage is 79%, 408 frontend tests pass, Svelte reports zero errors/warnings, the production UI
  builds, Ruff lint/format pass, migration smoke/path-matrix checks pass, documentation is
  consistent, and committed OpenAPI/client artifacts are current.

#### Full translation review 🌍
**Priority:** P1 | **Effort:** M | **Status:** ✅ Editorial sweep complete; independent native validation is not claimed ([design](docs/plans/2026-07-12-full-translation-review-design.md), [review](docs/reviews/2026-07-20-translation-editorial-review.md))

Review every locale against the `en.json` source of truth for completeness, accuracy, and
consistency; fix missing keys, drift, and machine-translation artefacts. Add CI checks so
translations can't silently rot.

✅ **Structural completeness** is finished: every locale now exactly matches `en.json`, including
shared controls, telemetry, update messaging, the Frigate media advisory, Dashboard audio copy,
Leaderboard source controls, and the complete Audio History surface.

✅ **Anti-rot CI is in place**: the audit rejects missing/extra keys and placeholder drift, asserts
a curated set of high-risk strings differs from English, and a baseline ratchet
(`locales.untranslated-regression.test.ts` + `locales.identical-baseline.json`) fails the build if
any *new* user-facing string lands byte-identical to English, so untranslated copy can't slip in.
The editorial gate additionally rejects encoding damage, surrounding whitespace, ASCII ellipses in
prose, known accent-loss substitutions, incorrect French double-punctuation spacing, and
sentence-length Latin-only copy in Japanese, Russian, or Chinese.

✅ **The application-wide editorial sweep is recorded**: all nine catalogs contain the same 1,981
leaf keys, interpolation tokens are preserved, and no sentence-length English copy remains in the
non-Latin catalogs outside technical examples. The pass corrected copied English enrichment copy,
accent-stripped settings and video-player text, Russian and Japanese phrasing, French punctuation
spacing, catalog whitespace, and application-wide ellipsis typography.

**Release limitation:** this was a repository-backed editorial and automated quality review, not
independent native-speaker certification. Before `3.0`, either obtain native sign-off for locales
presented as fully supported or state that limitation plainly in the release notes, as required by
the exit criterion above. No automated or structural defect remains open; independent reviewers
may still refine idiom and choose a single regional convention for the generic Portuguese catalog.

### 1.3 Candidate feature backlog — non-blocking for 3.0

Candidate features, roughly ordered by value. These can land before `3.0` when they are ready,
but otherwise remain post-3.0 backlog; they do not delay the release.

#### Finish multi-user: password reset + SSO 👥
**Priority:** P2 | **Effort:** M | **Status:** 🔄 Core shipped (v2.6.0), two gaps remain

JWT auth, registration/login/logout, Admin (Owner) + Viewer (Guest) roles, rate limiting, and
session management all shipped. Remaining:
- Self-service password reset flow (currently a manual `config.json` reset).
- Optional SSO (OAuth2: Google, GitHub).

#### Enhanced notification rules 🔔
**Priority:** P2 | **Effort:** S | **Status:** ☐ Not started

Per-platform filters, species whitelist, confidence/audio/camera filters, and delivery modes
already exist. Add a rule layer on top: time-of-day windows (e.g. only 7am–7pm), per-species
frequency limits (max 1/hr/species), weather-based rules, and custom message templates with
variables.

#### Video timeline & highlights 🎬
**Priority:** P2 | **Effort:** L | **Status:** 🔄 In progress

Automated highlight reels and time-based browsing. Shipped: video preview pipeline
(sprite/VTT + caching), expiring share links with watermark overlay + owner management, and a
day-bucket timeline strip with keyboard nav. Remaining:
- Fuller grouped-browsing timeline UI + advanced keyboard UX.
- Highlight scoring (confidence, rarity, activity) and clip stitching/preview thumbnails.

#### Durable media archive and retention floors 📚
**Priority:** P2 | **Effort:** M | **Status:** ☐ Proposed
([#178](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/178))

Favourites already protect their detection row and existing cached snapshot/clip from scheduled and
manual retention cleanup. Complete the stronger durability contract requested in #178: when a visit
is favourited, durably acquire its best snapshot and available clip into a dedicated archive before
Frigate rotates them; expose acquisition state and failures; and make unfavourite/archive deletion
an explicit owner choice. Add bounded rolling snapshot retention with both an age window and a
configurable per-species minimum, without automatically downloading every video.

**Acceptance:** archive writes are atomic and restart-safe; a favourite is not reported protected
until requested assets are durable (or an honest unavailable state is recorded); normal cache clear
cannot remove archived media; storage usage and destructive actions are visible; per-species floors
are canonical-taxon based; backup/restore is documented; and tests cover Frigate expiry, concurrent
favourite/unfavourite, partial downloads, cleanup order, and disk-pressure failure.

#### Analytics: insights panel + camera comparison 📊
**Priority:** P2 | **Effort:** M | **Status:** ☐ Not started

Charts (top visitors, daily histogram, seasonality, leaderboard trends, activity heatmap,
weather overlays) are shipped. Add: a confidence-distribution histogram, a camera-comparison
chart, and an insights panel (rarest sighting this week, best detection hour, weather correlation).

#### Advanced BirdNET-Go visualization 🎵
**Priority:** P2 | **Effort:** S | **Status:** 🔄 Mostly shipped; confidence fusion remains

Audio-visual correlation, buffering, camera↔sensor mapping, the recent-audio widget, spectrogram
visualization, authenticated clip playback, and the dedicated Audio History page are shipped.
Remaining: design and validate an explainable confidence-fusion score that combines visual and
audio evidence without overstating certainty.

#### Local LLM support (Ollama) 🏠
**Priority:** P2 | **Effort:** M | **Status:** ☐ Not started

Self-hosted LLMs via Ollama for privacy-conscious users: Ollama client, model selection UI,
vision-model support (LLaVA etc.), streaming responses, and clean fallback to cloud LLMs when
Ollama is unavailable.

#### Full DB backup/restore tool 💾
**Priority:** P2 | **Effort:** M | **Status:** ☐ Not started

CSV export (eBird format) is shipped. Add a first-class, safe full-database backup and restore
flow so users can snapshot and recover their detection history and config.

#### Home Assistant OS add-on 🏠
**Priority:** P3 | **Effort:** M | **Status:** ☐ Proposed ([#49](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/49))

Wrap the monolithic image as an installable HA Supervisor add-on so HAOS users can deploy from
the add-on store without a docker-compose stack. A companion `addon-yawamf` repo would carry the
add-on manifest, a Dockerfile pulling the published image, an apparmor profile, and Ingress
config; `/data` + `/config` map to the add-on data volume so upgrades preserve data and run
migrations. The existing `custom_components/yawamf` integration keeps handling the in-HA
sensor/event surface. **Out of scope:** replacing docker-compose (both ship side-by-side) and
embedding YA-WAMF in HA core. **Risks:** Ingress path-prefix CSP/CORS under `nginx + backend`;
ARM64 depends on the RPi image being production-ready (§2); a separate repo means ongoing
maintenance.

#### App-store templates & discovery 📦
**Priority:** P2 | **Effort:** M | **Status:** 🔄 Unraid template shipped; broader distribution not started

Make YA-WAMF easy to find and install where self-hosting, NVR, and media-stack users already
look. Keep the monolithic Docker contract stable across every template: image tag, web port,
Frigate URL, `/config`, `/data`, model/cache persistence, health check, optional hardware
acceleration, update-channel guidance, and a first-run smoke test.

- **Unraid Community Applications follow-through** — the Docker template and setup guide are
  shipped (`unraid/yawamf.xml`, `docs/setup/unraid.md`). Keep them synced with image names,
  ports, volume ownership, health checks, provider-family tags, and Intel GPU/NPU plus NVIDIA CUDA
  host guidance. The template keeps provider choice in-app instead of pinning it through an
  authoritative environment override. Next, pursue the normal Community Applications discovery
  path so users do not need to paste the raw template URL.
- **TrueNAS custom-app docs, then catalog submission** — first document the low-friction
  TrueNAS Custom App path for the monolithic image so users can deploy before catalog acceptance.
  Then submit a community-train app to `truenas/apps` using the current Docker Compose catalog
  structure: `app.yaml`, `ix_values.yaml`, `questions.yaml`, `README.md`, a Jinja2
  `templates/docker-compose.yaml`, and `templates/test_values/basic-values.yaml`. The wizard
  should expose the web port, Frigate URL, storage paths, CPU/memory limits, optional
  `/dev/dri` / accelerator device settings, a portal link, and a health check against
  `/health`. Validate with the TrueNAS apps render/deploy CI before opening the PR, and open a
  draft PR early to catch catalog-review issues.
- **Container registry discoverability** — continue GHCR publishing and add Docker Hub publishing
  once release tags are stable, with matching descriptions, README snippets, labels, supported
  architectures, and copy-paste compose examples for `latest`, pinned release tags, and `dev`.
- **Additional self-hosting templates** — add a Portainer stack/app-template example and evaluate
  CasaOS/ZimaOS packaging after the TrueNAS path settles. Consider YunoHost only if install,
  upgrades, storage, and reverse-proxy behaviour can be made appliance-like enough to maintain.
- **Project directories and community launch points** — submit or announce YA-WAMF in discovery
  channels that fit the app: Awesome Selfhosted, selfh.st/apps, AlternativeTo, the Unraid and
  TrueNAS forums, and relevant communities such as r/selfhosted, r/unRAID, r/truenas, Frigate,
  Home Assistant, BirdNET-Go, and homelab spaces. Use a short positioning statement, screenshots,
  setup links, and honest hardware/support notes rather than generic promotion.

### 1.4 Performance & reliability targets — non-blocking unless promoted

These are high-value follow-ups. A measured regression can promote a specific item into the 3.0
exit criteria; the broad initiatives do not block the release by default.

#### Performance optimization 🚀
**Priority:** P1 | **Effort:** L | **Status:** 🔄 Foundations in progress

✅ Connection pooling, route/locale lazy loading, bounded frontend work, and provider-family runtime
images are delivered. The full compatibility image remains available, while additive CPU, Intel and
CUDA images isolate large hardware stacks and remove build-only tooling/layers. Image promotion is
gated by per-flavor startup checks and a shared-volume full → CPU → full integrity round trip.
Runtime hardware validation is now governed by the same per-flavor contract, including CUDA in the
full image even when OpenVINO CPU is also present. Evidence is scoped per model to the exact image
flavor, failed reruns invalidate stale passes, and activation uses only a recommendation that still
matches the current eligibility record.
The first queue-reliability tranche is also delivered: MQTT intake starts after its consumers and
drains before they stop; distinct BirdNET observations are ordered and idempotent when BirdNET
publishes a stable ID; final Frigate events recover missed initial state; automatic video jobs are
reclaimed from durable detection status; and full-visit/HQ overflow uses bounded worker lanes with
reconciliation. Remaining: DB query optimization (indexes, optional result caching, cursor
pagination), a durable multi-process job broker only if deployment scale requires work beyond the
current single-container contract, targeted virtual scrolling, and a benchmark suite for
regression testing.

The species filter is the live instance and the reports disagree with the fix that has shipped.
Dropping the taxonomy join took the measured worst case from 247ms to 63ms, but
[#258](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/258) then reported the
opposite of what that predicts: a species with 2,700 detections loads in seconds while one with
under a hundred does not finish, and
[#301](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/301) is the same case at its
limit. Rarer being slower is the signature of `ORDER BY ... LIMIT` over a low-selectivity
predicate, where the planner walks the timestamp index backwards until it fills a page, so the
fewer rows match the deeper it reads. `resolve_species_aliases` is a second, fixed cost on the same
path: it selects distinct display names with ORs across four columns wrapped in `LOWER(...)`, the
exact shape the comment in `_canonical_species_query_parts` records as unservable by an index, so
it scans `detections` once per request before the slow part starts. Neither is addressed by an
index. Both want measuring on a database with a realistic long tail rather than on species counts
that happen to be healthy.

#### Keep the web service and ingest off the inference path 🧵
**Priority:** P1 | **Effort:** M

Tracked in [#312](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/312) and
[#313](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/313), both found while
diagnosing [#300](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/300).

MQTT ingest starts as a background task inside the API process, and with the default
`image_execution_mode: in_process` inference joins them on a `ThreadPoolExecutor`. Three tiers with
very different obligations therefore share one process, and nothing bounds how much CPU inference
takes: ONNX hardcodes `intra_op_num_threads = 4` regardless of the host, OpenVINO is configured
`PERFORMANCE_HINT: LATENCY` with no thread cap, and the container is shipped with no CPU limit.

It is already costing detections rather than just page loads. A reporter's bundle records
`save_and_notify` timing out after six seconds with `fault_drops: 1` and `critical_failures: 1`,
which is a lost detection and therefore a section 1 concern.

✅ The first slice is delivered: hardware capability detection no longer happens on a request. It
spawned up to three child processes, each importing an inference runtime with a five second timeout,
inline in an `async def`. A reporter's capture showed `/api/version`, which returns a fixed string,
waiting 22,551ms for its first byte with 0ms queued in the browser, alongside four other requests
finishing at the same instant. Detection now runs on a schedule off the request path and a status
read reports the age of its answer.

The outcome still wanted is a process boundary between tier 1 (ingest and the API) and tiers 2 and 3
(live, then background and video inference), plus CPU headroom so tier 1 is always schedulable. A
process boundary also makes a stalled inference killable, which an in-process thread is not: the
issue-33 plan records that the coordinator "cannot stop the underlying Python/native worker thread".

What blocks a default change is a measurement, not a decision. Memory per worker is one model copy
plus a 512MB crop detector, and the naive comparison is misleading: the same instance measured
633MiB immediately after restart and 4.815GiB after about a day, an eightfold growth with no change
of model. Any comparison between the modes has to be taken at a matched age over hours.

Complete when a fresh install runs inference out of process, resident memory is measured before and
after and stated honestly in the release notes, a test pins the resolved defaults, and Settings >
Detection explains the mode by its effect.

#### Find where the eightfold memory growth comes from 📈
**Priority:** P2 | **Effort:** S

The same instance, same model (`rope_vit_b14_inat21`, 361MB on disk), same configuration, measured
**633MiB immediately after a restart and 4.815GiB after roughly a day**. That may be OpenVINO arena
behaviour rather than a leak, but nothing currently distinguishes the two, and it decides whether
the worker-count question above is a real constraint or an artefact.

Complete when the growth curve is measured over days and attributed, and either explained as bounded
allocator behaviour in the docs or fixed.

#### Broader end-to-end coverage 🧪
**Priority:** P1 | **Effort:** M | **Status:** 🔄 Targeted coverage exists

Unit/integration tests, CI, coverage reporting, migration-safety checks, and startup smoke
checks are all in place. ARM64 image startup plus real model inference now run under QEMU before
mutable Raspberry Pi tags are promoted. The open work is expanding Playwright E2E coverage around
restart/recovery and GPU/provider fallback paths, plus a physical-Pi smoke/soak pass.

#### Crop-detector field benchmark 🐦
**Priority:** P1 | **Effort:** M | **Status:** 🔄 Production guard validated on Quark; broader owner-labelled promotion and replacement comparison remain

The evidence-only distant-subject threshold recovery is delivered, but a detector replacement is
not selected from one event or generic COCO AP. The production challenger now mirrors Frigate's
small-object advantage: it refines a same-frame tracked region with YOLOX, falls back from native
inference to four bounded overlapping tiles only on a miss, preserves full-frame evidence, and lets
the model crop replace Frigate only after a material downstream classifier gain. Frigate's final
clean best frame and snapshot-specific tracked-box crop are now protected completed-event baselines; bottom-centre
path geometry, end-event refresh, auditable fallback candidates, and non-duplicating temporal votes
are delivered. Build the remaining
manually labelled, visit-grouped Quark panel with near/distant birds and hard negatives; compare
Frigate, the optimized current YOLOX-Tiny path,
D-FINE-N, DEIMv2-N, RTMDet-Tiny, and PP-YOLOE+ S on downstream species correctness, crop recall/clipping,
false positives, and per-provider resource cost. D-FINE-N and DEIMv2-N have now failed the initial
varied-image localisation/negative screen: neither beat current YOLOX at a zero-field-false-positive
operating point, and both crashed inside the current Intel NPU compiler despite static batch-one
exports. They remain benchmark evidence, not runtime or release models. Promote only a reproducible
permissively licensed artifact that beats Frigate without weakening full-frame/fail-soft behaviour. See the
[candidate review and promotion gate](docs/reviews/2026-07-21-crop-detector-candidate-review.md).

The shared hardware sweep now includes both exact crop-detector artifacts, a species-diverse
round-robin image sample, deterministic hard negatives, isolated CPU/CUDA/OpenVINO compilation,
and CPU box/confidence agreement. The comparison fails closed on missing/duplicated rows and ignores
raw proposals below every production threshold. Validated crop providers activate at runtime with
CPU fallback. A private same-frame builder and initial 30-event/10-negative Quark panel now exist,
but most reference boxes and labels are still Frigate/automatic evidence rather than owner-labelled
ground truth. The reusable external-candidate probe, first D-FINE-N/DEIMv2-N CPU/Intel GPU/NPU
screens, schema-3 field manifest, and direct Frigate/model downstream win-tie-loss harness are
complete. The first optimized-path run used 24 guided, two sliced, and four fast-fallback positive
cases: the production guard promoted 7 same-identity crops with at least a two-point classifier gain
and retained Frigate for 23. The three owner-labelled cases produced one guarded improvement, two
ties, and no regression, while none of ten hard-negative regions produced a crop classification
above the active `0.40` floor.
That validates the fail-soft selection logic but is not enough owner truth to claim detector
superiority. Collecting more owner labels and comparing RTMDet-Tiny/PP-YOLOE+ S remain open.

#### High-availability setup 🏗️
**Priority:** P3 | **Effort:** M | **Status:** ☐ Not started

`/health` + Prometheus `/metrics` exist. Add example Nginx load-balancer config, session-less
multi-replica support, Grafana dashboard templates, and Kubernetes manifests.

#### Raspberry Pi hardware validation 🍓
**Priority:** P2 | **Effort:** S | **Status:** 🔄 Image ships; hardware validation remains

See [§2](#2-raspberry-pi-compatibility-best-effort) — the ARM64 image builds in CI; the open
work is real-device smoke/soak validation before declaring official support.

### 1.5 Technical debt — post-3.0 unless promoted

- **EventProcessor decomposition** (P2, M) — split `_handle_detection_save_and_notify` into
  smaller services (persistence, notification policy, media cache, auto-video trigger) to reduce
  coupling and improve testability.
- **BirdNET-Go audio backfill** (P2, M) — backfill BirdNET-Go audio detections into
  `audio_detections` so history regains audio context after a DB reset (needs a persistent
  BirdNET-Go source + importer + re-correlation).
- **Optional frontend log shipping** (P3, M) — optionally forward UI logs to a backend endpoint
  for remote debugging.
- **CSP tightening** (P3, M) — investigate moving from `unsafe-inline` to CSP nonces where feasible.

### 1.6 Engineering carry-overs — non-blocking

Small, incremental gold-standard follow-ups. They may land before `3.0`, but do not block it:

- **Frontend API contract adoption** — most SPA API modules now derive their types from the
  generated OpenAPI contract. Done: the email/iNaturalist integrations module, and the
  species module (search, eBird nearby/notable, seasonality, and the detections timeline all now
  carry backend `response_model`s and are consumed as generated types). Remaining, treated
  differently on purpose:
  - **`model_eval.ts` stays hand-written by design** — the model-eval `list_runs`/`get_run`
    endpoints return open-ended diagnostic JSON (the eval harness's `summary.json`, per-model
    metrics). A strict `response_model` would be brittle and could truncate diagnostic data, so
    `dict` is the correct contract; the module keeps a hand-written *view* type over it.
  - A few already-typed species endpoints (`stats`/`info`/`range`) still keep hand-written
    mirrors in `species.ts` — cosmetic, low priority.
- **Coverage ratchet** — raise the backend coverage floor as low-coverage modules gain focused tests.
- **Keep dated reviews current** as significant subsystems change.

### 1.7 Breaking changes & removals — required at 3.0

`3.0` is the version where deprecated paths are actually removed. These are already signalled
in-app and in docs; the release makes them final.

- **Monolith-only deployment.** The monolithic `nginx + backend` image becomes the *only*
  supported runtime shape. The legacy split `wamf-frontend` / `wamf-backend` deployment is
  removed from the default setup path and receives no further updates from `3.0`. Compose
  examples, CI, and reverse-proxy guidance assume the monolith by default.
  (Already flagged: [`docs/setup/migrate-split-to-monolith.md`](docs/setup/migrate-split-to-monolith.md).)
- **API-key auth removed.** Optional `X-API-Key` authentication is removed in favour of the
  password-based auth already available under Settings → Security. The deprecation notice is
  live today (`backend/app/auth.py`: *"API key support will be removed in v3.0"*); `3.0`
  deletes the code path.
- **Retired comparison-model downloads removed.** MogaNet-S EU, ConvNeXt-V1 Tiny EU,
  RegNet-Y-8G EU, and UniFormer-S EU are already absent from the current application catalogue.
  Their release assets remain temporarily available so pre-3.0 applications can still download
  them; the 3.0 release retires those legacy assets after the compatibility window.
- **Migration must be lossless.** Existing split-deployment installs must be able to move to
  the monolith with unchanged `/config` and `/data` volumes (DB, models, `config.json`), and
  the [split-to-monolith guide](docs/setup/migrate-split-to-monolith.md) stays the supported
  path through the transition.

**Acceptance:** `3.0` docs/compose/proxy guidance are monolith-first; the split path and
`X-API-Key` and the four legacy comparison-model assets are gone from the recommended/runtime
surface; a documented migration preserves all user data and runs DB migrations cleanly.

---

## 2. Raspberry Pi compatibility (best-effort)

**Status:** CI-built and QEMU inference-smoked ARM64 image available; not yet hardware-validated. Full assessment:
[`docs/reviews/2026-07-21-raspberry-pi-assessment.md`](docs/reviews/2026-07-21-raspberry-pi-assessment.md).

Release builds publish a dedicated ARM64 monolith image
(`ghcr.io/jellman86/yawamf-monalithic-rpi`); the web stack, MQTT, SQLite, and Nginx run on ARM64
unmodified, and the inference layer degrades to CPU-only (no CUDA / Intel iGPU-NPU / VideoCore).

**Shipped:** ARM-safe dependency selection (CPU `onnxruntime` plus standalone LiteRT, no x86 GPU
setup), a revision-pinned/checksum-verified bundled MobileNet fallback, Pi-aware first-run model
selection and download, functional Compose pressure controls, the multi-arch build job, and an
ARM64 QEMU gate that proves startup, classifier load, labels, and one inference before mutable tags
are promoted. Pi setup docs and `.env.rpi.example` match the deployed variables.

**Remaining:** a real-hardware exit pass (cold start, migration against preserved `/config` and
`/data`, sustained inference, thermal throttling, storage endurance, camera/event throughput, and
UI responsiveness) before claiming official support. Start with
`CLASSIFIER_IMAGE_MAX_CONCURRENT=1` and an SSD over microSD; measured device results must replace
estimates before publishing performance claims.

---

## 3. Delivered

Condensed — see [`CHANGELOG.md`](CHANGELOG.md) and git history for detail. Everything below has
shipped.

**Classification & models:** multi-model support (TFLite/ONNX: MobileNetV2, ConvNeXt, EVA-02),
fast-path mode, manual reclassification with the configured confidence guard, canonical
species-identity normalization, blocked-species picker with reliable taxonomy matching, manual-tag common-name
resolution, the classifier inference-health refactor (`v2.11`, issue #33 resolved), the labeled
feeder + auto-fetch model-evaluation harnesses, and the **accurate bird-crop detector tier**
(optional YOLOX-Tiny with fast→original fallback, model-manager UI, and adapter/eval tests), plus
**automatic per-model crop policy** validated on Quark and synchronized between the runtime registry
and downloadable model sidecars. The classification pipeline now also separates Frigate object and
sublabel confidence, runs local inference before trusted fallback, recovers missed MQTT `new` events
from `update`, protects manual identity atomically, uses sparse independent-moment deep-video
consensus (three separated evaluations, at least two confident votes, and a 60% winner), and
compares full-frame and cropped video evidence without double-counting frames, persists the winning
input provenance, aligns Frigate path coordinates to event and retained-recording timelines, and
surfaces provider failures for recovery instead of silently treating them as empty predictions.
Sparse dynamic crops use their own independent-moment denominator without requiring a fleeting
subject to occupy a fixed percentage of a long clip; centre-weighted sampling stays distributed,
and safe abstentions retain owner-visible per-source evidence instead of a generic no-result code.

**Acceleration:** Intel iGPU (OpenVINO), **Intel NPU** (`intel_npu` provider, capability probe,
device picker, validated per-model), and NVIDIA CUDA — all with empirical per-model validation and
clean fallback chains. The global registry separates safe providers from reviewed, host-gated
candidates; full audits can still probe undeclared providers without making them eligible.
Runtime selection, setup, Settings, and the activation API consume the same per-install measured
order, and schema-4 evidence expires across model artifacts, runtime stacks, visible accelerator
hardware, kernels, and image flavours. Reproducible release sidecars prevent older provider
metadata from narrowing or widening the current application contract. Crop-detector audits now use unique identities across a
round-robin clean species panel and hard negatives, fail on incomplete comparison coverage, and
test only proposals production could admit. The accurate YOLOX-Tiny tier is validated on Quark's
Intel CPU/GPU/NPU; the fast quantized SSD remains CPU-only. The 28 July 2026 full Intel audit
validated all 12 classifier entries that were present at the time and both crop detectors, followed
by explicit EU/NA family reruns after fixing human-readable country resolution. Its reviewed
candidate expansion is artifact-specific: NPU for Small Birds EU and Medium Birds NA, and GPU for
EVA-02 Large. The completed comparison also justified retiring MogaNet-S EU, ConvNeXt-V1 Tiny EU,
RegNet-Y-8G EU, and UniFormer-S EU from the current catalogue while retaining their release assets
for pre-3.0 clients. Medium Birds EU failed NPU CPU-equivalence and Small Birds NA produced
inconsistent NPU results, so neither route is selectable. The same audit narrowed
historically inconsistent GPU routes to host-gated candidates, with every installation required to
prove them before selection.

**Media & detection:** full-visit recording clips, HQ event/bird-crop snapshots with conservative,
an owner-only full-page manual-observation flow for photos and short videos with durable analysis,
explicit review, duplicate protection, production crop/temporal inference, and Frigate-independent
original-media retention, taxonomy and runtime provenance for uploaded-photo review, local history
thumbnails, omission of unrelated BirdNET-Go context, defensively extracted EXIF GPS with an
owner-editable optional map pin,
temporally independent multi-frame crop refinement for distant subjects, a protected Frigate final
best-frame baseline with correctly reconstructed bottom-centre path coordinates, recording-frame
classification fallback, media caching, and the video player with HTTP-Range seeking + expiring
watermarked share links. Playable partial recordings are retained instead of refetched forever,
corrupt media remains rejected, and HQ recovery has persistent bounded backoff across container
restarts. Manual temporal
reclassification follows the same best-available-media contract: complete cached recording →
decodable partial recording → cached event clip → Frigate event clip → snapshot fallback, with an
invalid cache entry unable to block the next usable source. It is owned by the bounded video queue,
deduplicates across manual/live/maintenance callers, reports Jobs progress, and isolates temporal
inference in a subprocess that can be terminated on cancellation or timeout.

**Integrations:** Frigate NVR (MQTT + media proxy), BirdNET-Go audio correlation, multi-platform
notifications (Discord/Telegram/Pushover/Email + Notification Center), BirdWeather, eBird (sightings,
maps, CSV export), iNaturalist (taxonomy + owner-reviewed submissions + seasonality), LLM behavioural
analysis (Gemini/OpenAI/Claude) with conversation history, and the **Home Assistant proxy/sidebar
panel** (ingress-authenticated dashboard).

**UI & platform:** real-time SSE dashboard, dark mode, advanced search/filtering, statistics +
leaderboard analytics, species detail modals, PWA baseline, complete i18n (9+ languages), the
settings architecture refactor + per-tab routing, a dedicated Jobs workspace, favourites, the
Explorer audio-matches filter, route-level and locale-level lazy delivery with resilient retry,
compressed immutable frontend assets, the in-app channel-aware update prompt, a grouped
status-aware desktop sidebar with a one-minute CPU/accelerator activity trace, and the Unraid Docker
template + setup guide.

**Backend & quality:** Alembic-only migrations, the repository pattern, opt-in anonymous telemetry
+ privacy-preserving daily rollups + replay-safe health identities + distinct aggregate User
Metrics/Health Data dashboards, backfill service, health checks + Prometheus metrics, weather
enrichment, password-based + optional API-key auth (timing-safe), connection pooling, global
exception handling, bounded background-work lanes with owner-visible server status and restart
recovery for automatic video jobs, a typed OpenAPI contract with generated SPA types, and the CI
enforcement suite (lint/format/coverage/OpenAPI-drift/type-freshness/migration-safety).

---

## Contributing

Everyday work happens on `dev`; release tags / `main` are handled separately. Every change clears
the [`CLAUDE.md`](CLAUDE.md) contract — safety, test-first, reversible migrations, clean UI, and the
Definition of Done — before it is committed. New roadmap work should land a dated design note under
[`docs/plans/`](docs/plans/) when it starts, and move to the [`CHANGELOG.md`](CHANGELOG.md) +
[Delivered](#3-delivered) when it ships.
