# Codebase optimisation and refactor review

Date: 1 November 2026. Reviewed head: `e8a6110936195aa1d66fbf2a77863e48fc95af64`.

Scope: the specified current-dev review checkout, repository history, static analysis, an isolated settings reproduction, frontend checks and build, and backend test durations. This is a review, not an implementation or a formal security audit. No application, test, migration or configuration changes were made. No Docker commands, deployments, live services, live databases or dependency installation were used. Tests use private disposable fixture storage on the original SSD; model directories are empty. Findings below distinguish observed behaviour, static operation counts and risks that still need benchmarking.

## 1. Summary

The codebase has a sound safety contract and substantial machinery that implements it. Keep the reversible, two-stream Alembic setup, unique ingest identities, preservation of owner corrections, bounded inference admission, subprocess crash isolation, explicit public-media rules, generated API artifacts and the existing frontend kit. The review checks found clean Ruff, Svelte and dead-code gates. This is not a case for replacing the stack or rewriting the product.

The main cost is that application policy and lifecycle state accumulate in a few busy files, then tests pin the shape of those implementations. The six largest backend modules contain 27,696 lines, 26.3% of backend Python. October history contains 32 non-merge commits touching Explorer, 30 touching the classifier and 27 touching Settings. Source-reading tests occupy 126 of 286 frontend test files. Those are maintenance concentration measures, not proof that every long function is wrong.

One finding is an observed correctness problem: an invalid settings request can alter public access before returning an error. An isolated call enabling public access and supplying an invalid notification address returned HTTP 400 with public access changed from false to true in memory. That deserves a regression fix before broader extraction.

The five highest-value changes are: make settings updates validate and persist before publication; replace implementation-pinning lifecycle assertions with executable behavioural tests; remove changelog merge contention with per-change fragments; share the existing bird/Garden pagination lifecycle behind typed adapters; and batch owner audio-context reads. Typed classifier status and test-resource ownership follow closely. Settings tab loading and classifier extraction have larger benefits but need several small PRs, not a single structural rewrite.

Garden duplication is real at infrastructure boundaries, but a universal bird/animal persistence pipeline would erase useful distinctions. Share loaders, presentation contracts and transport mechanics. Preserve Garden's confirmation, person-veto, attachment provenance and delivery-attempt rules as explicit policies. The recommendations supplement the 30 October UI audit with structural causes and current measurements; they do not reopen its already-fixed colour, label-fetch, modal-loading or guest-polling findings.

## 2. Hypotheses tested

| Hypothesis | Verdict | Evidence and qualification |
|---|---|---|
| 1. God modules | Confirmed | `classifier_service.py:2002`, `:2981`, `:5501`, `:7113` contains adapters, runtime control, input selection and video execution. `detection_repository.py:5414` embeds audio persistence in a 190-function file. `Settings.svelte:215`, `:1778`, `:3071`, `:3471` owns 204 state initialisers, dirty detection, hydration and saving. See F09-F12. Size and recent churn both justify action. |
| 2. Garden duplicates birds | Partly confirmed | Two 73/70-line capture loaders share 52 exactly matching stripped lines; four notification channels are implemented twice. However `garden_notifications.py:1`, `:25`, `:52` documents deliberately different cooldown/freshness rules, and `garden_media_cache.py:320` serialises publication with privacy revocation. `garden_public.py:21` already reuses the shared public windows. Share mechanics, not one database or one admission policy. See F04, F08, F13. |
| 3. Source-text tests | Confirmed, with valuable exceptions | 126/286 frontend test files read source, including 101/102 files named `*.layout.test.ts`. The scan counted 2,813 `toContain`, `toMatch`, `toEqual` or `toBe` calls in source-reading files; not all target source strings. `events-request-lifecycle.layout.test.ts:13` proves that variable spellings exist, not that stale requests lose. Conversely locale parity and architecture prohibitions have real static value. The standards explicitly request diagnostic wiring tests at `diagnostics-and-dialogs.md:72`; retain those or amend that contract explicitly. F02. |
| 4. Merge friction | Confirmed, not inevitable | October: 256/325 non-merge commits touch `CHANGELOG.md`, and 109 touch each locale. Merge messages explicitly record changelog conflicts in 50 merges and conflicts in every locale in three merges. Examples: `3a2384db`, `4cf8bdb3`, `79e3cc99`. This is measured contention, not a claim that every simultaneous edit conflicts. F03. |
| 5. Inconsistent building blocks | Partly confirmed | `score-tone.ts:1`, `status-tone.ts:1`, `single-flight.ts:8`, `lazy-component.ts:6`, Settings primitives and `DiagnosticDialog` already exist. Do not create replacements for them. `ExplorerFilters.svelte:292` hand-builds choices beside `SettingsSegmented.svelte:53`; the two visit loaders duplicate lifecycle mechanics. The giant Settings form is confirmed, but one deliberate Apply remains appropriate for worker-changing settings. F04, F09. |
| 6. Slow, fragile feedback | Partly confirmed | The serial gate has a 480-second subprocess deadline (`run_regression_gate.py:15`, `:41`); no xdist dependency is declared. Global test setup migrates even for pure logic (`conftest.py:55`), patches aiosqlite threads into daemons (`:17`) and restores singleton state (`:180`). 107/417 backend test files import `app.main`; 37 contain positive numeric sleeps. Those are isolation warnings, not proof all sleeps are flaky. Chromium already has two workers and zero retries (`playwright.config.ts:14`); its reported five-minute duration was not remeasured. See measurements and F07. |
| 7. Configuration sprawl | Confirmed in mapping, not storage choices | 24 config-model classes have 257 annotated fields, including nested objects and helper entries. `load_settings_instance` is 751 lines; `SettingsUpdate` has 207 fields; the update handler is 743 lines. Configuration is represented again in frontend state and a hand-maintained response interface. Environment over file over defaults is a useful contract, and an atomic persisted file is appropriate. F01, F09. |
| 8. Defensive complexity | Partly confirmed | Native-crash preservation in `d5cf8446` and privacy generation checks at `garden_media_cache.py:327` guard demonstrated failures and should stay. A production branch detecting monkey-patched queues (`broadcaster.py:41`) and an obsolete commented test hook (`conftest.py:188`) have no comparable product value. Hardware compatibility, stale-result guards and fail-closed identity checks are not noise merely because they are long. F15. |

Paths in the hypothesis table are abbreviated. Backend service paths are under `backend/app/services`, repository paths under `backend/app/repositories`, and frontend paths under `apps/ui/src/lib`, unless stated otherwise.

## 3. Ranked findings

Rank reflects value relative to initial implementation effort, adjusted for safety and churn. S means up to half a day, M one to two days, L roughly three to five days, and XL a multi-PR programme. Estimates include tests and review, not calendar promises. For larger findings the first PR is specified separately.

### F01. Stage settings updates before publishing them

**Area:** backend configuration and public-access safety. **Effort: M. Risk: high if handled incorrectly.**

**Problem and evidence.** `backend/app/routers/settings.py:1806` mutates the live global object throughout a 743-line handler. Public access changes at `:2298`, but notification-address validation can still reject the request at `:2419`; persistence occurs only at `:2505`. In a disposable process, `SettingsUpdate(public_access_enabled=True, notifications_instance_url='not-a-url')` followed by a direct call to the handler returned 400 while the live flag changed from false to true. No server, external service or database was involved. A file-write failure presents the same ordering risk, although that path was not reproduced. Initial auth setup already restores prior state on save failure (`backend/app/routers/auth.py:456-477`, tested at `backend/tests/test_auth_endpoints.py:250`), a useful local precedent. Blame traces the late URL rejection to `ccdc0364`, rather than a recent Garden addition.

**Change.** Add `services/settings_update.py` with `prepare_update(current, patch) -> PreparedSettings` and `apply_update(prepared)`. Build and fully validate a deep candidate, calculate side effects, persist the candidate atomically, then publish to the existing settings facade under one update lock. Schedule worker reloads and broadcasts only after success. Retain the current endpoint and flattened DTO initially. Readers holding nested settings references need a deliberate publication strategy; do not casually rebind a singleton imported by other modules.

**Safety and verification.** Add the combined invalid-address/public-access case to `backend/tests/test_settings_api.py:18`; assert both memory and saved file are unchanged. Add persist-failure and concurrent-update tests. Retain `test_settings_update_inference_provider.py`, `test_settings_backup.py`, `test_public_settings_projection.py` and redacted-secret round trips. An invalid or failed update must change zero settings and schedule zero side effects.

### F02. Replace source-pinned lifecycle tests with executable contracts

**Area:** frontend testing and refactor cost. **Effort: M for the first group; XL for the whole inventory. Risk: medium.**

**Problem and evidence.** Source readers account for 126/286 frontend test files and 8,410 lines. `apps/ui/src/lib/pages/events-request-lifecycle.layout.test.ts:13` asserts three exact strings involving `eventsLoadGeneration`; `Settings.route-split.layout.test.ts:43` asserts the text of a comment. Renaming a correct implementation breaks these tests, while putting the same strings in an unused branch can satisfy them. This is a false-confidence risk, not a measured failure rate or a claim that the tests make CI slow.

**Change.** First extract a request-generation controller and pure settings-route normaliser. Test two deferred promises resolving out of order, abort ownership, access changes and legacy route normalisation directly. Keep one fixture-browser case for the route/DOM wiring. Then migrate snapshot, polling and modal lifecycle assertions when those areas change. Keep static tests for forbidden inline fetch/`any`, locale parity and intentionally mandated shared-dialog wiring. Update `docs/standards/diagnostics-and-dialogs.md:72` and `layout-patterns.md:601` only if changing their structural-testing requirement.

**Safety and verification.** Land behavioural coverage before deleting each source assertion. `apps/ui/src/lib/utils/garden-visit-capture-list.test.ts:17` demonstrates executable loader testing already available in the repo; the bird loader has only source-wiring coverage in `components/visit-captures.layout.test.ts:67`, so add its behavioural contract before extraction. Assert stale data cannot return after owner-to-guest transitions and that failed loads remain distinguishable from empty data. Do not reduce the test count as an end in itself.

### F03. Remove the shared edit points in change records and translations

**Area:** workflow and translation maintenance. **Effort: M overall; changelog fragments are an S first PR. Risk: low to medium.**

**Problem and evidence.** `CHANGELOG.md:7` is the insertion point for nearly every branch; the file has 6,315 lines and was touched by 78.8% of October non-merge commits. Nine locale files each have 4,196 lines. Git merge messages explicitly list 50 October changelog conflicts and three conflicts per locale. `apps/ui/src/lib/i18n/locales/en.json:620`, `:2843`, `:3945` already delineates Settings, events and Garden domains, but all share a file.

**Change.** First propose a contract amendment allowing one `changelog.d/<issue-or-branch>.md` fragment to satisfy CLAUDE.md §6, with a deterministic release assembler preserving the human-first release standard. This is an explicit proposed standards change, not current compliance. Separately split locale authoring by existing top-level domain, loading and merging only the selected language through the existing retrying loader (`apps/ui/src/lib/i18n/index.ts:37`). Keep key names stable. Partition locale inputs for editing; do not commit a second generated aggregate that every feature must update. Domain splitting reduces cross-feature overlap, not contention between two changes to the same domain.

**Safety and verification.** Preserve all nine languages, exact flattened keys, placeholder parity, ICU plurals and duplicate-key rejection. Migrate locale tests and loader imports in the same PR and compare flattened dictionaries byte-for-byte before and after. Backend notification locales are separate and need no migration. Release assembly must fail on duplicate or malformed fragments and produce a deterministic result. These changes reduce review conflict work, not runtime latency by themselves.

### F04. Share the paged capture lifecycle through typed adapters

**Area:** bird/Garden frontend infrastructure. **Effort: S. Risk: medium because access is part of cache identity.**

**Problem and evidence.** `apps/ui/src/lib/utils/visit-capture-list.svelte.ts:15` and `garden-visit-capture-list.svelte.ts:14` are 73 and 70 lines, with 52 exactly matching stripped lines. Both implement page size 20, abort ownership, keyed results, loading/error state, append/reset and disposal. The differences are endpoint shape, membership key and history invalidation. They already use different deep/raw state for the same immutable-page pattern.

**Change.** Extract `PagedCaptures<T>` with injected `key()`, `readPage({offset, limit, signal}) -> {items, total}` and access-aware invalidation. Retain the two current public classes as adapters, preserving every domain-specific key term. This is a concrete first shared observed-subject boundary without changing storage, visits or permissions. Apply `$state.raw` to immutable page snapshots.

**Safety and verification.** Port the existing Garden loader tests and add bird-adapter cases to a shared contract suite covering initial load, duplicate trigger, reset, append, failure, disposal and late response. Include an owner-to-guest transition and Garden review that renames a position stack. Keep `browser-tests/garden-*` record-refresh coverage; identity changes must invalidate the old key before results can render.

### F05. Batch owner audio contexts and avoid materialising irrelevant rows

**Area:** event presentation and data access. **Effort: M. Risk: medium.**

**Problem and evidence.** `backend/app/routers/events.py:822` loops over events with unconfirmed audio and makes one awaited `get_audio_context` call per qualifying owner event at `:836`. `backend/app/repositories/detection_repository.py:5653` fetches every visible audio row in each time window, then filters mappings, parses payloads, sorts and finally slices at `:5700`. For M qualifying events this adds M SELECTs, so a 50-event page with 50 qualifying events adds 50 context queries, before localisation. That is a source-derived operation count, not a measured live request latency. Guests already use a batch at `events.py:804` and must not regress.

**Change.** Add `AudioHistoryRepository.contexts_for_events(events, mapping, scope)` that coalesces overlapping time intervals, reads bounded chunks once per merged interval and distributes rows using one pure mapping/ranking function. Start with removing repeated reads for overlapping windows. Preserve nearest-time then confidence ranking, per-event limits and exact suppressed counts where the detail API needs them. A naive SQL LIMIT before sensor filtering would change results and is not acceptable.

**Safety and verification.** Extend `backend/tests/test_events_audio_context_api.py:52` with 50 qualifying records and a context-query-count assertion that 50 overlapping windows require one interval read when the fixture fits one batch. Retain `test_audio_public_bounds_and_identity.py:192` for boundary clipping and `test_public_audio_mapping_and_portraits.py`. Include hidden audio, wildcard and unmapped sensors, overlapping windows, equal-distance ranking and timestamp boundaries. Benchmark seeded fixtures before considering an index migration; this review establishes no missing or unused index.

### F06. Give operational classifier status a real generated contract

**Area:** API types and runtime-state honesty. **Effort: M. Risk: medium.**

**Problem and evidence.** `backend/app/routers/classifier.py:133` publishes `/status` as `dict[str, JsonValue]`; `apps/ui/src/lib/api/classifier.ts:4` independently specifies the operational shape and casts the response at `:110`. Its own comment at `:10` explains that subprocess mode omits `loaded`, `error` and `enabled`. The UI audit's wrong loaded-state interpretation is a concrete example of the risk, although its UI fix is already present. The checked OpenAPI has 242 operations; 15 JSON-200 schemas are open maps or empty shapes, including diagnostic endpoints where openness is legitimate.

**Change.** Add a stable `ClassifierStatusResponse` with explicit runtime source, effective model, health, execution mode and optional typed sections for workers/crop detection. Generate frontend types and remove the parallel hand-written status DTO. Keep debug/probe payloads open where the standard permits exploratory diagnostics. In the first PR, preserve existing optionality and response fields rather than redesigning the public endpoint.

**Safety and verification.** Contract-test representative in-process, subprocess-not-started, ready, fallback and quarantined states. Keep generated-artifact freshness gates. Exercise `backend/tests/test_classifier_supervisor.py` and frontend `utils/pipeline-health.test.ts`; absence of a local model must not imply inactive subprocess classification. Validate the unauthenticated response as well as the owner response.

### F07. Make tests own resources before attempting parallel execution

**Area:** backend feedback and lifecycle isolation. **Effort: L for the first fixture boundary; XL for broad isolation. Risk: medium to high.**

**Problem and evidence.** `backend/tests/conftest.py:55` creates/migrates a suite database before collection even for pure tests. Six autouse fixtures restore or clean shared state at `:127` onward. The daemon-thread patch at `:17` explicitly exists because connections outlive their event loops; its rationale is understandable, but it masks incomplete ownership. The comment at `:124` says tempfile handles cleanup, while `mkdtemp()` at `:64` has no automatic deletion. 107/417 backend test files import `app.main`, and per-file restoration is ad hoc (`test_settings_api.py:25` restores a selected list of global attributes). The CI gate is serial and bounded at 480 seconds. Nine schema-sanity tests each run a full migration chain (`backend/tests/test_sqlite_schema_sanity.py:7`, `:31`, `:51`), accounting for roughly 20 seconds among the measured durations. This repeated setup is a smaller, safer feedback win than dropping migration coverage.

**Change.** Introduce opt-in migrated-history and app-resource fixtures. Move pure tests under a subtree without database/singleton autouse setup. As an S first slice, create one migrated schema-sanity template and copy it into each private fixture; keep tests that specifically verify migrations running the real upgrade/downgrade chain. Give connections, dispatcher tasks and clients explicit context-managed owners and loop-aligned scopes. Keep an app factory accepting settings/resource providers behind the current app facade. Once this is proven, shard or use xdist only on isolated groups, with worker-specific paths and bounded native worker counts. Keep the daemon workaround until a leak-detection lane proves it removable.

**Safety and verification.** Run the same affected tests in normal and reversed group order, then in independent processes. Track open connections, active children and tasks at teardown. Retain subprocess exit and SIGTERM/SIGKILL tests; they need real processes. Replace clock-dependent scheduling sleeps with injected time/events where feasible, not all sleeps mechanically. Duration results below are local, not a CI speed-up guarantee.

### F08. Separate notification messages and delivery policy from transport

**Area:** bird/Garden backend reuse. **Effort: M. Risk: high around repeat delivery and secrets.**

**Problem and evidence.** `backend/app/services/notification_service.py:319`, `:392`, `:444`, `:521` implements Discord, Pushover, Telegram and email. `garden_notification_transport.py:114` implements the same four channel APIs again and reaches through `notification_service.client` at `:120`. Telegram has duplicated escaping, caption limits, photo/text branches and buttons; email separately assembles inline attachments at `:189`. October commits `f8c3820f` and `2736950e` fixed Garden notification/media parity gaps. Similar mechanisms do not justify a common notification eligibility rule.

**Change.** Add `notifications/message.py` (`NotificationMessage`, optional bounded attachment, subject link) and `notifications/transports/{discord,telegram,pushover,email}.py` with `send(message, credentials, options) -> DeliveryResult`. Keep bird and Garden message builders and their existing dispatch/claim policies. Inject transport clients; stop exposing one service's client as the other's dependency. Port Garden first, then birds, one channel at a time.

**Safety and verification.** Preserve Garden's one-attempt-per-channel-per-visit claim and bird cooldowns independently. Retain `backend/tests/test_garden_notifications.py:325`, `:354`, `:384`, `:397`, `:482`, `:508`, `:536`, `test_notification_service.py` and secret-redaction tests. Assert exact multipart shape, escaping, no credential-bearing media URLs and privacy recheck immediately before sending. Add common transport conformance tests without replaying failed sends.

### F09. Replace settings field choreography with section adapters and lazy controllers

**Area:** configuration architecture and Settings UI. **Effort: XL overall; first section M. Risk: medium to high.**

**Problem and evidence.** `backend/app/config_models.py:185` onward defines 24 model classes with 257 annotations. `config_loader.py:226` is a 751-line loader, including defaults, environment parsing, aliases and old-config migrations. `routers/settings.py:802` repeats 207 update fields and `:1541` serialises the settings response in 262 lines. Frontend `Settings.svelte` has 204 state initialisers, dirty comparison at `:1778`, loading at `:3071` and a large full-form payload at `:3506`. Eleven tab/page components import synchronously at `:104`, in addition to Garden. The emitted Settings chunk is 679.25 kB raw / 171.74 kB gzip, the largest JavaScript chunk in this build.

**Change.** Keep the precedence contract and persisted JSON. Extract a typed descriptor per section: environment aliases, patch-to-model mapping, secret treatment and required side effects. Use model defaults rather than retyping them in the loader, but retain explicit compatibility migrations. Start with Appearance, comparing old/new loaders and projections. In the frontend add `settings-draft.svelte.ts` plus section `decode`, `encodePatch`, `validate`, `dirty` adapters. Lazy-load tab bodies with existing `lazyComponent` and route loading/error UI. Keep one deliberate Apply; compose section patches rather than introduce competing independent saves. Reuse existing `SettingsSegmented` or a narrowly generalised accessible choice primitive when touching duplicated control markup, not a new kit.

**Safety and verification.** Preserve omitted/null/empty/REDACTED semantics and environment precedence; preserve secret masks and legacy aliases. `SettingsResponse` is already generated dynamically from update fields at `routers/settings.py:1350`, so do not build another response schema generator. Use `test_config_env_mapping.py`, `test_settings_backup.py`, settings API tests and frontend section tests. Rebuild after each tab extraction and record actual chunk reductions. F01 precedes this work. Do not promise that splitting source alone reduces shipped bytes.

### F10. Extract classifier policy, adapters and input selection behind the facade

**Area:** inference architecture. **Effort: XL overall; each initial extraction M/L. Risk: high.**

**Problem and evidence.** `backend/app/services/classifier_service.py` has 7,883 lines and 237 functions/methods, 13 at least 100 lines long. Distinct responsibilities are runtime adapters at `:2002-2980`, provider-selection policy at `:1470-1828`, stateful recovery at `:3743-4244`, input/crop/provenance decisions at `:5501-6198` and video execution at `:7113-7883`. October brought 30 touches and 974 changed lines. Model registry ownership already exists in `model_manager.py`; a second registry would worsen the split.

**Change.** First move pure preprocessing/output helpers and model adapters into `inference/adapters/` under an `InferenceAdapter` protocol (`load`, `classify_raw`, `probe`, `close`). Then extract `provider_policy.py` returning an immutable selection/fallback plan, and `input_selection.py` returning an image plus typed provenance. Move stateful recovery only after introducing an explicit `RuntimeState` owned by the existing supervisor/facade. Keep `ClassifierService` as the import-compatible facade and retain worker serialization/version contracts.

**Safety and verification.** Preserve label-width/artifact checks, finite-output checks, host validation, CPU fallback and quarantine. `d5cf8446` fixed loss of native crash status; that complexity has a demonstrated reason. Run provider, preprocessing, admission, supervisor, native CPU recovery and worker protocol suites after each move. Compare deterministic fixture outputs and status snapshots. Hardware performance remains a separate authorised hardware gate, not a justification to remove protective state machines during this review.

### F11. Split detection data access by responsibility without changing transactions

**Area:** repositories and dependency direction. **Effort: XL overall; audio extraction L. Risk: high.**

**Problem and evidence.** `backend/app/repositories/detection_repository.py` has 6,210 lines and 190 functions/methods. It owns photo candidates (`:691`), identity/filter SQL (`:988`), writes (`:1986`, `:2160`), rollups (`:4565`) and audio ingest/history (`:5414`). Audio insertion calls a service to resolve identity at `:5447`; audio context imports the audio service parser at `:5660` expressly to avoid a circular dependency. `taxonomy/taxonomy_service.py:260` also owns raw cache SQL, despite the repository contract. October had 13 touches; August-October had 64 and 3,260 changed lines.

**Change.** Start `AudioHistoryRepository` with unchanged SQL/commit boundaries and make `DetectionRepository` delegate. Move shared BirdNET payload/mapping parsers to a pure audio payload module used by both layers. Next extract `SnapshotCandidateRepository`, `DetectionQueries` and `SpeciesRollupRepository`. Keep identity/alias SQL builders shared and parameterised. Introduce `TaxonomyCacheRepository` separately. Avoid a mixin collection, cross-database joins or commits silently introduced by a new repository.

**Safety and verification.** First run old and delegated facades over identical seeded fixtures and compare results. Preserve unique Frigate/BirdNET ingest identities, manual corrections, soft deletion and all visibility filters. Retain `backend/tests/test_detection_repository.py:927`, `:964`, `:1034`, `:1079`, snapshot-candidate tests and audio idempotency tests. Schema and indexes need no change for extraction; any later change requires its own reversible migration.

### F12. Make video/HQ processing explicit stages with typed results

**Area:** hot-path orchestration and evidence ownership. **Effort: XL overall; one stage L. Risk: high.**

**Problem and evidence.** `backend/app/services/auto_video_classifier_service.py:1574` contains an 815-line `_process_event`; classifier `classify_video` at `:7113` is 536 lines. HQ snapshot processing mixes durable scheduling (`high_quality_snapshot_service.py:249`), candidate generation (`:798`), scoring (`:874`), count evidence (`:1230`) and frame selection (`:3284`) across 3,763 lines. The classifier and HQ paths repeat parsing of Frigate path points (`classifier_service.py:5531`, `high_quality_snapshot_service.py:2020`). This is primarily change/correctness cost; inference speed gains are not established.

**Change.** Extract pure `frigate_track.py` parsing first. Introduce typed `VideoWorkInput`, `SampledFrames`, `ClassificationDecision` and `EvidenceCommitPlan`. Keep the current coordinator, leases and durable scheduling, but have it delegate acquisition, sampling, model evaluation, admission and evidence commit to separately testable stages. Reuse shared frame/input utilities; preserve distinct photo-choice and counted-bird evidence rules. Do not turn all stages into background tasks or change ordering to claim parallelism.

**Safety and verification.** Keep `test_auto_video_classifier_snapshot_upgrade.py`, `test_hq_snapshot_film_alignment.py`, `test_final_snapshot_candidate_ownership.py`, `test_recording_snapshot_input.py` and HQ service tests. Exercise cancellation at every awaited stage, retry after partial work and preservation of owner-selected evidence. Commit atomicity and stale-generation guards must remain visible in the orchestration contract.

### F13. Centralise detection presentation and use a discriminated subject view

**Area:** router layering and cross-surface parity. **Effort: M for bird presentation; L for subject-view adoption. Risk: high for guest projection.**

**Problem and evidence.** `backend/app/routers/events.py:753` is a 265-line presentation pipeline with media, taxonomy, audio and access shaping. `routers/species.py:1285-1316` and `routers/stats.py:584-615` contain an identical 31-line localisation/species/audio block, followed by separate DTO construction. A whitespace-normalised 12-line clone scan found 21 overlapping windows in that pair. Garden owns its own projection in `routers/garden.py:151` and public handling at `:208`. The risk is divergent fields and public behaviour, not that every projection is already wrong.

**Change.** Add `services/detection_presenter.py` with `present_many(rows, context)`, where context carries language, timezone, access scope and preloaded media/audio/name maps. Make events, stats and species delegate without introducing router-to-router imports. On the frontend use `ObservedSubject = BirdSubject | GardenSubject` and shared visit/media view contracts with typed capabilities, keeping different review actions and counters explicit. Classification taxonomy and display subject are separate: domestic birds can intentionally belong to Garden.

**Safety and verification.** Golden response comparisons for owner and guest across all three bird surfaces, including camera masking, public audio windows, hidden captures and omitted owner fields. Use existing event/stat/species API tests plus `test_garden_visitors.py` and `test_public_settings_projection.py`. Make restricted information absent or redacted according to the existing endpoint contract; do not fetch privileged data and rely on UI hiding.

### F14. Move catalogue resolution off the async audio-write path

**Area:** async correctness and ingest latency. **Effort: S. Risk: medium.**

**Problem and evidence.** `backend/app/repositories/detection_repository.py:5466` synchronously calls `resolve_audio_identity` while assembling parameters inside an async insert. That calls `species_catalog_resolver.resolve_scientific_name` (`audio_identity.py:41`), which calls `_ensure_loaded` (`species_catalog_resolver.py:458`). Every resolution performs a filesystem stat at `:98`; a changed catalogue synchronously reloads output/name tables through sqlite3 at `:115-150`. This is one sync resolution per inserted audio row. Event-loop blocking is established from the call path; its milliseconds and catalogue size were not measured against live data. Detection writes already show the safe off-thread precedent at `detection_service.py:148`.

**Change.** Resolve identity with `await asyncio.to_thread(...)` before entering the write transaction, ideally in the ingest service, then pass `species_id` to the repository. Preserve the resolver's fresh catalogue and ambiguity semantics rather than replacing it blindly with a potentially stale in-memory lookup. Combine with F11 only after the small safety-preserving async fix.

**Safety and verification.** Existing audio-identity, audio-idempotency and catalogue-resolution tests; add a barrier-controlled resolver test proving another coroutine runs while resolution is blocked. Verify missing, changed and ambiguous catalogues still allow ingest with no guessed identity. No schema change or catalogue rewrite is required.

### F15. Remove production branches whose only consumer is a test double

**Area:** defensive complexity. **Effort: S. Risk: low.**

**Problem and evidence.** `backend/app/services/broadcaster.py:41` inspects whether `queue.put` was monkey-patched and changes from non-blocking delivery to awaiting that method. The corresponding test at `backend/tests/test_broadcaster.py:95` patches `put`, although production uses `put_nowait`. Blame dates the branch to `689cf08a`, so it is stable, low-churn cleanup rather than an urgent defect. `backend/tests/conftest.py:188-196` retains an obsolete commented skip hook that conflicts with the no-commented-out-code rule. These are two concrete examples, not a basis for deleting all defensive code.

**Change.** Make the broken-queue test fail through the actual non-blocking boundary, then remove the monkey-patch branch; delete the obsolete hook comments. Keep bounded queues, slow-subscriber removal, exception handling and the classifier singleton replacement guard (`classifier_service.py:1972`), whose stale-instance problem is documented as issue #50. Do not remove compatibility code merely because it mentions a historical incident.

**Safety and verification.** Run broadcaster fan-out, backpressure, concurrent subscription and failed-queue tests. Assert one slow subscriber cannot delay another. No application or persistence behaviour should change.

## 4. Target architecture

Keep FastAPI, Svelte 5, SQLite/aiosqlite, ONNX/OpenVINO/TFLite and the existing supervisor/admission model. The brief describes async SQLAlchemy, but current detection repository runtime access is aiosqlite (`backend/app/database.py:7`, `repositories/detection_repository.py:616`); an ORM migration is not needed.

The backend should have HTTP routers composing injected services; services preparing decisions and owning orchestration; repositories owning history/catalogue/cache reads and writes; and pure modules owning identity, mapping, admission and presentation policy. Inference adapters, selection policy, input preparation and lifecycle coordination should have separate ownership. Import-compatible facades let callers move gradually. The application lifespan should own clients, workers and dispatchers; tests substitute those providers without rebuilding the whole application for pure decisions.

An observed subject is a discriminated application/view contract, not a new universal table. Birds retain durable detection identities, corrections and integrations; Garden retains confirmed/review states, privacy vetoes and its own delivery claims. Shared capabilities can describe a photo, clip, paginated captures, taxonomy or notification message, but authorisation and provenance decide whether each capability is available. No shared default grants an animal the bird pipeline's permissions, or counts a domestic Garden bird in wild-bird totals.

Settings retain environment precedence and the persisted file. A staged update service consumes explicit section adapters, validates a complete candidate, persists and then publishes it. The frontend owns one draft composed of section states and one intentional Apply, while tabs load independently. Existing kit controls, `score-tone`, `status-tone`, `lazyComponent`, single-flight and focus-management utilities remain the building blocks. A generic cached GET must accept explicit access/language/window keys and eviction rules; do not merge caches simply because they all contain a Promise.

The test pyramid should have many pure rule/controller tests with fake clocks and deferred promises, repository tests on privately migrated fixtures, API contract and permission tests with injected resources, and a smaller set of browser workflows proving rendered accessibility and request behaviour. Real process crash/deadline tests stay as a focused integration tier. Narrow static architectural/locale assertions stay, while spelling-sensitive tests of dynamic behaviour are retired only after replacement coverage lands.

## 5. Sequenced, independently shippable plan

Every step is a short-lived branch from current dev and a PR to dev, with existing gates green. No step requires a deployment or data rewrite as part of the refactor. Larger findings are deliberately decomposed here.

| Step | PR scope and acceptance | Dependencies |
|---|---|---|
| 1 | **Safety first:** reproduce F01 in the existing settings API suite, move all rejecting validation before mutation as the smallest fix, and prove invalid requests do not alter state. | None. Quick containment; the persistence-failure case still needs step 2. |
| 2 | Introduce candidate/persist/publish settings updates and serialised writers; preserve the public endpoint and add failure/concurrency tests. | 1. Unblocks config adapters. |
| 3 | **Quick win:** correct broadcaster test boundary and remove only the test-specific branch/obsolete hook. | None. F15. |
| 4 | **Quick win:** extract pure request/route controllers and replace the first lifecycle source assertions, keeping fixture-browser wiring coverage. | None. F02; supports later UI extraction. |
| 5 | **Quick win:** typed paged-capture engine with unchanged bird/Garden adapters and access-transition tests. | 4 useful, not required. F04. |
| 6 | **Quick win:** async catalogue identity resolution, with no SQL/schema change. | None. F14. |
| 7 | Changelog fragments plus the explicit contract/release-documentation amendment and deterministic assembler. | None. F03 part 1. |
| 8 | Batch overlapping owner audio contexts with query-count and result-equivalence fixtures. | None; use existing repository facade. F05. |
| 9 | Define typed operational classifier status, generate types, remove the hand-written DTO. | None. F06; supports inference extraction. |
| 10 | Isolate pure-test setup from database resources; then add owned async-resource fixtures. Keep the serial lane until teardown is proven clean. | None. F07, two PRs. |
| 11 | Port Garden Telegram transport to the typed message interface, then bird Telegram; repeat for the other channels in separate PRs. | None. F08; conformance tests first. |
| 12 | Extract Appearance config/draft adapter; lazy-load one Settings tab and compare save/load behaviour and build output. Repeat one section per PR. | 2 and preferably 4. F09. |
| 13 | Move audio repository/parser responsibilities behind the current facade. Split rollup/photo query ownership in later PRs. | 8 and 6 reduce interference. F11. |
| 14 | Extract bird presenter without changing endpoint outputs; migrate stats, then species. Introduce subject view adapters separately. | 8 helpful. F13. |
| 15 | Extract classifier preprocessing/adapters, then pure provider policy, then input selection. Change recovery ownership only after typed runtime-state tests exist. | 9; 10 helpful. F10. |
| 16 | Extract shared Frigate path parsing; turn one video acquisition/sampling stage into a delegate; follow with typed evidence commit plans. | 15 input boundary helpful. F12. |
| 17 | Partition locale authoring and migrate all nine language loaders/tests, preserving flattened dictionaries. | 7 is independent. F03 part 2. |

Steps 10-17 should be scheduled around feature work, not as a frozen-codebase campaign. Keep wrappers until their callers migrate, but remove them once unused rather than allowlisting dead code. None of these steps needs a big-bang replacement. Every extraction must preserve the same transaction, cancellation and access boundaries before changing behaviour in a later PR.

## 6. Measurements and method

### Source inventory and churn

Counts include blank/comment lines. Backend counts cover `.py` files in `backend/app`, not migrations, tests or JSON assets. Frontend counts cover files under `apps/ui/src`; the often-quoted approximately 98,000 excludes locales and generated API code. Here that comparable count is 99,651; including both is 142,823 across 652 files. Counts are not complexity scores.

Churn uses reachable non-merge commits dated 1-31 October 2026 and, separately, 1 August-31 October. A touch is a commit/path occurrence, not a PR. Changed lines are additions plus deletions from `git log --numstat`; renamed/deleted historical paths can appear, so the priority table below uses current paths. These windows contain 325 and 773 non-merge commits respectively.

| Current path | Lines | October touches | October changed lines | August-October touches |
|---|---:|---:|---:|---:|
| `backend/app/services/classifier_service.py` | 7,883 | 30 | 974 | 59 |
| `backend/app/repositories/detection_repository.py` | 6,210 | 13 | 678 | 64 |
| `backend/app/services/high_quality_snapshot_service.py` | 3,763 | 17 | 1,044 | 31 |
| `backend/app/services/auto_video_classifier_service.py` | 3,354 | 20 | 553 | 34 |
| `backend/app/routers/settings.py` | 3,351 | 21 | 346 | 50 |
| `backend/app/routers/proxy.py` | 3,135 | 15 | 650 | 32 |
| `apps/ui/src/lib/pages/Settings.svelte` | 4,247 | 27 | 571 | 50 |
| `apps/ui/src/lib/components/DetectionModal.svelte` | 3,912 | 28 | 986 | 80 |
| `apps/ui/src/lib/pages/Events.svelte` | 2,538 | 32 | 1,747 | 50 |
| `apps/ui/src/lib/pages/Species.svelte` | 2,316 | 13 | 345 | 31 |

`DetectionModal` is the largest current UI hotspot over the longer window. Its snapshot request state at `:325`, reference lookup at `:1185`, conversation at `:1282` and actions at `:1540-1759` are useful controller seams. Extract those as feature work touches them, using F02's behavioural-test approach, rather than split markup by line count. The current modal chunk is already lazy, so this is a maintenance recommendation, not a repeat of the old eager-modal audit finding.

Garden-specific backend service files number 23 and total 4,519 lines; five repositories add 1,570 lines and the router adds 709. Those name-based counts measure footprint, not duplicated lines. October history records concrete parity work: `f8c3820f` for alerts, `2736950e` for kept media and `9c72a806` for following a renamed position stack.

### Largest functions

Python AST spans include signature, body and comments inside the function, excluding decorators.

| Function and evidence | Lines |
|---|---:|
| `auto_video_classifier_service.py:1574` `_process_event` | 815 |
| `config_loader.py:226` `load_settings_instance` | 751 |
| `routers/settings.py:1806` `update_settings` | 743 |
| `classifier_service.py:7113` `classify_video` | 536 |
| `model_eval_service.py:310` `_do_run` | 484 |
| `classifier_service.py:4245` `_init_bird_model` | 436 |
| `detection_service.py:884` `apply_video_result` | 384 |
| `routers/stats.py:828` `get_detection_timeline_span` | 314 |
| `event_processor.py:575` `_process_event_payload` | 313 |
| `main.py:517` `lifespan` | 294 |

All paths except explicit `routers/`/`main.py` entries in that table are under `backend/app/services`, apart from `config_loader.py` under `backend/app`.

### Duplication and test-shape counts

- Backend Python: 256 files, 105,341 lines.
- Frontend tests: 286 `.test.ts`/`.spec.ts` files; 102 named `*.layout.test.ts`; 126 read source through `?raw`, `readFileSync` or `readFile(...)`. These categories overlap. 101 layout-named files are source readers; the remaining layout-named test checks destructive-action locale wording.
- Source-reader files contain 8,410 lines and 2,813 calls to four common assertion methods. This deliberately broad inventory includes useful locale/style tests; it is not an assertion-by-assertion audit.
- Backend tests: 417 `test_*.py` files. 107 contain a direct `from app.main import`; 37 contain numeric positive `asyncio.sleep`/`time.sleep` calls. Indirect imports and computed sleep values are not counted.
- Bird/Garden page loaders share 52 exactly matching whitespace-stripped lines, measured with `SequenceMatcher` over 73 and 70 lines. Empty/brace lines count, so this is a modest local clone measure, not a percentage of removable product code.
- Exact stripped 12-line windows with at least nine non-comment/nonblank lines and 300 characters find 21 overlapping matches between species and stats presentation. The longest matched block is 31 lines; the count also includes adjacent DTO construction, not 252 independent duplicated lines. Another 23 overlapping matches between backfill/settings include DTO declarations; move those only when their semantics and contract ownership agree.
- Changelog: 256 touches, versus 109 per locale. Of 274 October merge commits, 50 contain explicit conflict lists; every one lists the changelog and three list all nine locales. This is a lower bound from recorded messages, not an exhaustive merge-conflict reconstruction.

### Read-only checks and build

| Command | Result | Local wall time |
|---|---|---:|
| Existing backend venv `ruff check . --no-cache` | Passed | 0.09 s |
| `npm run check` | 0 errors, 0 warnings | 17.27 s |
| `npm run lint:dead` | Passed | 2.87 s |
| Existing Vite binary `build --outDir /tmp/yawamf-review-build` | Passed; Vite phase 8.59 s | 9.62 s |

Independent frontend measurements ran concurrently, so these are observed shared-host timings, not isolated benchmark medians. No dependency was installed. The Vite binary came from the pre-existing symlinked `node_modules`.

| Emitted chunk | Raw kB | Vite-reported gzip kB |
|---|---:|---:|
| Settings | 679.25 | 171.74 |
| hls | 574.41 | 178.97 |
| Events | 168.36 | 44.82 |
| Entry index | 159.57 | 46.54 |
| DetectionModal | 135.61 | 36.94 |
| Dashboard | 96.28 | 26.93 |
| English locale | 220.96 | 69.54 |
| Entry CSS | 183.39 | 28.64 |

The English gzip row is copied from the build log and should be interpreted as a compressed asset, not initial JavaScript. A static-import walk of emitted JavaScript found 400,860 raw bytes across 27 files reachable from the entry; the initial 500 KiB budget passed (`apps/ui/vite.config.ts:8`). The same walk from Settings reaches 967,089 bytes across 36 files, including shared dependencies, so that is not Settings' incremental download cost. Lazy hls, lazy locales and record dialogs are not automatically part of the entry. No live HTTP, startup, model inference, browser render, RSS or idle-network benchmark was performed.

### Backend durations

The full serial measurement used the existing Python 3.12 venv, `pytest tests/ -q --tb=short --durations=50 -p no:cacheprovider`, bytecode disabled, and private SSD fixture/config/catalogue/model paths. It reported **6,816 passed, 54 skipped, two failed and ten setup errors in 454.79 seconds**; process wall time was 460.64 seconds. All 12 unsuccessful cases were `FileNotFoundError: alembic`, caused by this review invocation using the venv interpreter without adding its `bin` directory to `PATH`, not by an observed application regression. After correcting `PATH`, the three affected files passed **12/12 in 40.84 seconds**, process wall time 43.57 seconds. Thus every previously failing case passed on the targeted rerun; this is not a claim of a second, clean full-suite run.

No coverage collection was enabled, so compare cautiously with the 480-second coverage-enabled CI gate. The run reported 5,437 warnings, including deprecated `datetime.utcnow` calls. Empty model directories intentionally skip installed-model/hardware validation; these results establish no hardware accuracy or performance.

| Slow case from the full run | Phase | Seconds | Evidence |
|---|---|---:|---|
| Failed conversation cleanup rolls back analysis replacement | call | 6.03 | `backend/tests/test_ai_regeneration_integrity.py:207` |
| Media-job migration round trip and parent guards | call | 4.88 | `backend/tests/test_media_job_durability_migration.py:12` |
| Initial classification provenance preserves history | call | 4.76 | `backend/tests/test_initial_classification_migration.py:8` |
| Content-hash migration preserves photo candidate rows | call | 4.68 | `backend/tests/test_photo_retention.py:210` |
| Classifier-input migration preserves identity through rollback | call | 4.58 | `backend/tests/test_initial_classification_migration.py:51` |
| Initial setup restores memory after config-save failure | call | 4.23 | `backend/tests/test_auth_endpoints.py:250` |
| Garden kept-media migration preserves history | call | 3.91 | `backend/tests/test_garden_kept_media_migration.py:15` |
| Garden owner-correction migration round trip | call | 3.89 | `backend/tests/test_garden_owner_migration.py:12` |
| Scheduler metrics observe circuit/maintenance waits | call | 3.01 | `backend/tests/test_auto_video_classifier_queueing.py:369` |
| Schema sanity, nine separate full upgrades | call | 2.17-2.28 each | `backend/tests/test_sqlite_schema_sanity.py:7` |

The corrected rerun measured audio-visibility migration at 4.98 seconds and bird-observation migration at 4.92 seconds. Rollup tests repeatedly spent 1.61-1.74 seconds in per-test migration setup (`backend/tests/test_rollup_canonical_identity.py:33`), in addition to their call phase. Together with the nine schema-sanity upgrades, these support sharing a migrated baseline for ordinary schema/reader tests while preserving dedicated reversible-migration tests. The long integrity cases test useful guarantees; this review does not recommend deleting them to make the gate faster.

Final report validation: the documentation consistency check passed and validated 242 routes; `git diff --check` passed. The report is the sole untracked repository addition and remains uncommitted.

### Reproduction and reproducibility limits

The isolated settings script creates fresh configuration/media/model paths on the developer SSD, imports the handler without starting the app, and invokes it with the two-field patch in F01. Output: `status 400 setting_before False setting_after True changed_despite_error True`. It exercises the actual handler and Pydantic patch, not a reimplementation; it does not claim a browser exploit or that persistence changed.

Counting/reproduction scripts and measurement logs are throwaway `/tmp/yawamf-review-*` artifacts, not committed project files. Commands use the specified backend venv and installed frontend dependencies. Only this report is a requested repository addition. No coverage percentage, live query latency, index usefulness, saved memory or expected speed-up is inferred from source size.

## 7. Not recommended

- **A universal observed-subject table or ingest rewrite.** Garden privacy, review, native model evidence, domestic routing and notification claims differ materially. A discriminated view and shared mechanics provide reuse without moving history or weakening vetoes.
- **Replacing SQLite, adopting a new ORM or adding a general event bus.** No measured storage-engine bottleneck justifies migration risk. Fix query repetition and transaction ownership first. Keep the two catalogue/history migration streams independent.
- **Adding indexes speculatively.** Lowercased species/time indexes already have migrations (`backend/migrations/versions/a7c4e2f9d1b3_index_species_names_with_time.py:39`). This review did not run representative EXPLAIN plans or establish unused indexes. Any index work needs seeded workloads and a reversible migration.
- **Turning on xdist immediately, or increasing native-worker counts.** Global fixtures and loop-bound resources need isolation first; parallel model tests can multiply memory. Keep deadlines and real subprocess regression tests.
- **Deleting all layout tests.** Locale, architecture and required diagnostic-wiring checks remain valuable. Replace implementation-sensitive behavioural claims incrementally, preserving coverage first.
- **Autosaving settings or converting every tab to independent writes.** Workers restart and settings interact; an intentional Apply is still right. Improve the draft/update boundaries while retaining atomic validation and honest feedback. This agrees with the prior UI audit's recommendation.
- **Replacing the UI kit, Svelte, Chart.js, markdown-it or hls.js.** Existing helpers and lazy loading are functional. Share small demonstrated seams instead of building a second design system or a universal cache framework.
- **Removing fail-closed guards, native recovery or privacy checks to shorten files.** Their history and tests demonstrate real failure modes. In particular keep crash-signal preservation, admission bounds, owner correction protection, checksum provenance and delayed person-veto publication checks.
- **Mass reformatting, blanket comment deletion or a repository-wide rename PR.** Ruff already passes. These would create churn precisely where contention is highest, with little user or engineering value.
- **A dedicated optimisation campaign for low-churn diagnostic tooling before the busy paths.** The 484-line model-evaluation runner deserves eventual stage extraction, but October classifier/Explorer/settings changes and the reproduced settings failure have clearer immediate value.
