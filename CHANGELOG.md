# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

### Added

- **Diagnostics now name the sources the species catalogue is built from, and their licences.** The
  catalogue redistributes work from the IOC World Bird List under CC BY 3.0 and the Catalogue of
  Life under CC BY 4.0, both of which require attribution, and nothing in the running application
  showed it: the Naming Sources card reported how many species the catalogue held but not where any
  of them came from. It now lists each pinned source in the active release with its version,
  licence, and citation as the source gave it, so the attribution belongs to the release actually
  running rather than to whatever the documentation last said. Alongside it, in plain words: the
  catalogue is a separate file from your detection history, rolling one back changes names and
  never your recorded sightings, and a backup of the data directory covers both. Documented in full
  under Taxonomy & Naming.

- **A catalogue release may now name an output the catalogue could not name before.** Until now a
  release carrying any different mapping for an already-registered model failed the whole import
  closed, which is right for a mapping that rewrites what an output is, but also blocked one that
  merely fills a gap. An output held as `unknown` with no species carries no claim: it records the
  model's label and says nothing about what it is, so a release that can name it is adding
  knowledge rather than correcting a claim. That one difference is now applied. Every other
  difference still fails the release closed: an identity being replaced or withdrawn, a label being
  rewritten, or a class kind moving anywhere else.

- **A model you installed yourself can now be identified by the species catalogue.** Every model in
  the registry ships a reviewed output mapping, so the catalogue can say what each of its classes
  is; a model an owner supplied had none, so its detections never gained a canonical identity and
  its `labels.txt` stayed the only thing that knew what its classes were. Such a model now gets a
  mapping derived from its own labels, resolved against the live catalogue. It refuses to guess: a
  label reaches an identity only through an exact catalogue match, and only when every way of
  reading that label agrees, so a name two species share and a name that is one species' English
  name and another's scientific name both resolve to nothing rather than to the wrong bird. Every
  output it cannot name is still recorded, carrying the model's verbatim label, and reported in
  owner diagnostics under `species_catalog.local_mapping`. A registry model is skipped outright so
  a mapping derived from a file on disk can never stand in for a reviewed one, an artifact the
  catalogue already holds is never overwritten, and these labels are never served back as
  catalogue-verified — they came from the label file this work exists to stop trusting. If that
  model is later published, the reviewed mapping replaces the derived one: a mapping compiled from
  a file on disk was never authoritative, and refusing the release because it disagreed with one
  would block every future catalogue update for that owner.

- **Audio detections carry catalogue identity.** Audio correlation was the last read path keyed on
  name text, so a bird heard and a bird seen were joined by a string. BirdNET-Go reports a
  scientific name and a scientific name moves. Audio detections now record a `species_id` at
  ingest, resolved by the same conservative rule the detection backfill follows: a name the
  catalogue holds for exactly one species gains that identity, anything ambiguous or unknown gains
  nothing and behaves exactly as before. Existing rows are filled in by a background backfill,
  which is required rather than optional: grouping by identity while older rows had none would
  split a species at the upgrade boundary. On a live install this identified 55,998 of 56,026
  audio detections across 84 species, and the counts are unchanged today.

- **Installed models can be deleted from Settings > Detection.** Models are the largest thing
  YA-WAMF writes to `/data`, and there was no way to remove one: the only route was emptying the
  directory and downloading again whatever was still wanted. On one reference deployment that left
  3.8 GB of models, including a single 1.2 GB model that was not in use. Each installed model now
  offers **Delete files**, which reports how much space it reclaimed. The active model cannot be
  deleted, nor can one that is mid-download, and the confirmation names the model and says it can
  be downloaded again. Region variants such as `medium_birds/eu` are addressed individually, and an
  emptied family directory is tidied up behind them.

- **The clock format is now yours to choose.** Settings > Appearance gains a time format control
  alongside the existing date format: follow the browser, 12 hour, or 24 hour. Pinning the date
  format previously left the clock to the browser's locale, so choosing `DD/MM/YYYY` on a US
  locale produced `22/08/2026 1:45:00 PM`, a European date beside an American clock in the same
  string. The date format description no longer claims to cover times, because it never did.
  Also available as `DISPLAY__TIME_FORMAT`. Requested in #247.

- **Every identity-writing pipeline now speaks the same canonical language.** Video refinements
  shadow-resolve their winning output through the catalogue before replacing a primary
  identification, with a guard so a queued result applied after a model switch is never
  attributed to the wrong artifact. Manual observations attach canonical identity only when the
  chosen name resolves to exactly one catalogue species, and carry no artifact provenance because
  a manual identity is human-asserted. Historical backfill imports already resolve through the
  shared save path.

- **Existing detection history gains canonical identity where it is certain.** A conservative
  backfill runs detached at startup: a row whose recorded scientific name resolves to exactly one
  catalogue identity (a concept or a recorded synonym) gains a `species_id`; an ambiguous name, a
  name no held source carries, or a row without a scientific name stays exactly as it is and is
  counted. Nothing else is written — name snapshots, artifact provenance, and already-assigned
  identities are never touched, re-running is a no-op, and the outcome is reported in the Health
  payload beside the shadow statistics.

- **New detections now carry canonical catalogue identity, shadow-verified.** Phase 3 of the
  versioned species catalogue begins: every live classification records which model artifact
  (by checksum) and output index produced it, and gains an opaque `species_id` only when the
  catalogue and the existing label path agree on the identity — a recorded synonym counts as the
  same bird. Disagreements are counted and surfaced in the Health payload's shadow statistics
  and withheld from history rather than persisted; a missing catalogue or unregistered model
  degrades to exactly the pre-catalogue behaviour. The three new detection columns arrive by a
  reversible migration and the historical name snapshots are untouched.

- **Settings > Health now reports the species catalogue honestly, in every language.** The Naming
  Sources card shows whether a catalogue is present, how many species it holds, and states in
  plain words how many model output classes still have no catalogue identity and keep their
  original label text, so a number is never left to explain itself. Behind it, a new status
  service reports the active catalogue release, per-artifact mapping coverage, and an activation
  check that resolves a model checksum directly against the catalogue and verifies the output
  tensor width, with `unregistered`, `incomplete_mapping`, and `width_mismatch` verdicts. The
  check is advisory until label-file authority is retired before 3.0, because several supported
  models still carry honestly-unresolved classes.

- **Every supported classifier's outputs are now mapped in the catalogue by model checksum.** A
  deterministic compiler resolves each output index of every registry artifact through the seed
  catalogue by its declared label grammar: 21,650 of 23,332 indices resolve to canonical species
  identities (an apostrophe-insensitive match recovered most of the measured European shortfall,
  and taxonomy synonyms like iNat21's *Bufotes balearicus* land on their accepted identity),
  `background` and `Unknown` are declared class kinds, and 1,679 unresolved indices remain visible
  gaps rather than guesses ([coverage report](docs/reviews/2026-08-20-model-output-mapping-coverage.md)).
  The committed mapping record ties to the registry by regression test, the seed build folds it
  into `model_artifacts` and `model_output_taxa`, and release imports carry mappings with the
  artifact checksum owning its mapping set.

- **The species catalogue now knows the 8,514 non-bird classes the wildlife models can emit.**
  Their scientific names are resolved against the pinned Catalogue of Life COL26.7 release
  (admitted through the provenance gate, with the export digest now recorded in the source
  manifest): 7,536 exact accepted matches, 342 resolved through unambiguous synonyms with the
  label text kept as an alias, 12 taxonomy lumps sharing one identity, and 636 unresolved classes
  recorded explicitly rather than guessed
  ([report](docs/reviews/2026-08-20-col-nonbird-mapping-report.md)). The committed identity
  artifact folds into the seed build, so a fresh installation's catalogue covers birds and
  non-birds alike, and release imports carry aliases with the same never-guess semantics.

- **Catalogue releases can now be imported transactionally, and rolled back.** A built release
  bundle is validated (schema revision, exactly one release row, recorded content digest recomputed
  in canonical order, foreign-key integrity) and then staged and activated inside a single
  transaction against the live catalogue; interruption at any point leaves the previous release
  active with no partial rows. Species identity is stable across releases — a taxon already known
  through a provider concept keeps its `species_id`, identities are never deleted, and names from
  every release coexist with their provenance — so rolling back to a retired release is one
  reversible state change. Owner overrides are never touched, and re-importing the same bundle is
  a no-op.

- **A fresh installation now starts with a complete species catalogue.** The image builds a
  deterministic seed release of `/data/species_catalog.db` from the committed IOC reference
  (11,276 species with their translated names, admitted through the source provenance gate), and
  first start copies it into `/data` atomically. An initialisation marker distinguishes a genuinely
  fresh install from a catalogue that has gone missing: a lost catalogue may have held owner
  enrichments, so it is reported and left for the owner instead of being silently replaced by the
  seed. A seed that fails its recorded digest is refused, and none of this can block startup.

- **The species catalogue database now has its own versioned schema.** Phase 1 groundwork for the
  versioned species catalogue: a dedicated, single-head Alembic stream
  (`backend/alembic_catalog.ini`, `backend/migrations_catalog/`) creates `/data/species_catalog.db`
  with the full designed schema — opaque species identity with synonym links, provider taxon
  concepts, RFC 5646 translated names, fail-closed aliases, checksum-keyed model artifacts, the
  output-index mapping with declared class kinds, transactional release records (at most one
  active), and owner name overrides that survive refreshes. Constraints live in the schema, the
  stream is reversible and idempotent, and CI now smokes it and enforces one head per stream
  alongside the detections database.

- **The species catalogue's sources are now a frozen, machine-checked contract.** Phase 0 of the
  versioned species catalogue: `backend/app/assets/species_sources.json` pins every source species
  data may come from — the IOC World Bird List 14.2 already bundled, Catalogue of Life COL26.7
  (DOI 10.48580/dgyhw) for canonical taxonomy, the eBird 2025 taxonomy as the runtime crosswalk,
  and an explicit refusal to redistribute iNaturalist data — each with its licence, citation, and
  redistribution decision. The reference builder now refuses a source outside that manifest or an
  input file that is not the pinned release. A generated inventory
  (`docs/reviews/2026-08-19-species-catalogue-phase0-inventory.md`) covers 100% of supported model
  artifact checksums with their label grammar and measured name resolution, and a regression test
  keeps it current with the registry.

- **Legacy Intel GPU compute support for Gen8, Gen9, and Gen11 hardware.** The `full` and `intel`
  images now include Intel's pinned `legacy1` OpenCL and Level Zero packages alongside the modern
  driver stack, restoring OpenVINO discovery on hardware such as Coffee Lake. Every downloaded
  package is checksum-verified, and the install retains the current `libigdgmm12` instead of
  downgrading a shared modern-driver dependency
  ([#177](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/pull/177)).

- **Bird names can now be in your language without the internet too.** The bundled reference ships
  English, so a locale you have already pulled from eBird is kept beside the database and used when
  nothing is reachable. It is fetched in one request per language rather than one per species, and a
  name eBird returns unchanged from English is not recorded as a translation.

- **Bird names now work offline, in your language, with no account.** The bundled species reference
  is now the IOC World Bird List: 11,276 species with names in all eight non-English languages the
  app presents, redistributed under CC BY 3.0. Italian goes from almost nothing to 90% and Chinese
  to complete, the European models resolve about 90% of their species locally instead of a third,
  and an eBird key is no longer needed for any of it. eBird remains as an enhancement for species
  the list does not carry.

- **A newly installed model can name birds offline straight away.** The naming maps were built once
  at start, so on a fresh install, where nothing is downloaded yet, a model chosen in the setup
  wizard had no local names until the next restart. Installing a model now rebuilds them, and
  changing your eBird key or language now refetches the local names for it.

- **The European bird models can now name most of what they detect offline.** Their labels are
  common names, so nothing could be derived from the file itself and they resolved barely a third of
  their species locally. Each label is now matched to a scientific name once, against the bundled
  reference and then eBird, taking `flexivit_il_all` and `eu_medium_focalnet_b` to about 79%.

- **Settings > Health now says where bird names come from.** A new Naming Sources card reports how
  many species can be named without the network, which languages are held locally, and whether any
  model's label file has stopped matching the checksum it was published with. A changed label file
  names every detection from it wrongly, and that was previously visible only in a log line.

- **Model label files are now checked against the checksum they were published with.** They were
  verified once at download and never again, so a label file altered afterwards was read as
  authoritative and every detection classified against it was recorded under the wrong species. The
  verdict appears in classifier status, and a file that no longer matches is not used to build the
  species mapping.

- **The bundled species reference is checked before it is trusted.** It ships with a recorded
  checksum and is refused if it does not match, because a reference altered on disk would write
  wrong species names into your history. Regenerating it produces a byte-identical file, so the
  checksum can be verified rather than taken on faith.

- **Bird names now resolve without the internet where we can ship them.** A bundled species
  reference covering 964 species answers when iNaturalist cannot, so an offline install, or one
  riding out a provider outage, still names the bird instead of showing a bare label. iNaturalist
  still answers first when it is reachable, so nothing loses the taxon identity enrichment depends
  on.

- **Diagnostics bundles now say how your clips are packaged.** Safari refuses HEVC tagged `hev1` in
  a video element while QuickTime plays it happily, so "the download opens fine" never settled
  whether the packaging was the problem. A bundle now reports the sample format of a recent clip and
  whether Safari will accept it, read straight from the container without needing ffmpeg in the
  image. There is a new troubleshooting page covering the fix and the two things about it that are
  easy to miss ([#167](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/167)).

- **The Health page now says how the feeder is doing in colour, not just in a badge.** The status
  card takes the verdict itself: green when everything is healthy, amber when something is waiting on
  you, red on a failure, and slate for a state that has not been measured. Counts that described the
  diagnostics export rather than the feeder have moved out of the reading, and the export itself is a
  compact panel behind a disclosure instead of a two-column library.

- **The Health page opens with what your feeder actually did.** Visits it recorded and frames it
  filtered out now share one thread, in the order they happened, rendered by the same `FieldLog`
  timeline the dashboard uses rather than a second idiom. Every figure on the page describes one
  window, measured from when the instance started, and each filtered frame carries its picture on
  hover or keyboard focus, degrading to a placeholder once Frigate has rotated it away. Subsystem
  cards keep all of their detail behind a disclosure below.

### Fixed

- **The interface no longer slows to a crawl, or stops loading entirely, while the server waits on
  something that is not the database.** The server keeps five database connections and serves every
  request from them. A request handler is meant to hold one only while statements are running, but
  a number of them held one for the whole handler, including the parts that wait on Frigate, on the
  weather archive, on an AI model, or on image classification. A connection carried through an AI
  analysis is a fifth of the server's capacity spent waiting on someone else's network for as long
  as that call takes. Enough of those at once and there is nothing left for anything else: the
  dashboard takes fifteen seconds, Settings takes twenty, the live-updates stream drops, and a page
  that should be instant never arrives. Reported as slow dashboards and events that would not load,
  with diagnostics showing requests queued behind the pool for as long as 17.8 seconds.

  Ten handlers now read what they need, release the connection, do the slow work, and take a
  connection again to write: AI analysis, AI chat, chart analysis, snapshot reclassification,
  wildlife classification, the species filter, the two dashboard timeline endpoints, both weather
  backfills, and the unknown-detection batch scan. Measured against a copy of a real installation,
  with twenty-four concurrent requests against the same five connections, the median request went
  from 2.3 seconds to 0.2, and the longest a request spent waiting for a connection went from 4.7
  seconds to 0.18.

  The species filter is the one most likely to have been noticed. It resolves a name for every
  species it offers, five at a time against five connections, and each species not yet cached costs
  an iNaturalist request with a ten-second timeout, all of it under a connection the handler was
  also holding. Six other read paths still resolve names under a held connection on a cache miss;
  they are listed in `ISSUES.md`, they are bounded to the first sighting of a species in a given
  language, and the pool now names them in the log and in a diagnostics bundle when it happens.

- **Concurrent reclassifications can no longer deadlock the server outright.** Reclassifying a
  detection held a connection and then called the routine that saves the result, which takes a
  second connection of its own. With as many reclassifications running at once as the pool has
  connections, every one of them held one and every one of them was waiting for one that only
  another waiting request could release. Nothing completed, nothing timed out, and the server
  stayed that way until it was restarted. The reclassification path no longer holds a connection
  while it works, so the second one is always free to take.

- **A saturated connection pool now says so, instead of hanging.** Waiting for a connection had no
  upper bound, so a request could sit behind a stalled pool indefinitely while the browser gave up
  and the log recorded nothing. Requests now wait up to twice the SQLite busy timeout — sixty
  seconds by default, comfortably longer than any legitimate wait, including a write blocked on the
  database lock — and are then refused with a plain 503 and a `Retry-After`, which is honest about
  it being a busy moment rather than a fault. The log records which code was holding a connection
  longest at that point. Set `DB_POOL_ACQUIRE_TIMEOUT_SECONDS=0` to wait indefinitely instead.

  Ingesting a detection is exempt from that deadline and always waits. Frigate and BirdNET-Go each
  deliver an event once, and both handlers turn any error into a logged drop, so refusing one of
  them a connection would lose a sighting rather than delay it. The exemption travels with the task
  rather than being passed down through the event processor, the detection service and the
  repositories by hand, so no layer can forget to carry it.

- **The pool now recognises the shape that caused the deadlock, before it bites again.** A task that
  holds a connection and asks for a second is what made concurrent reclassification stop dead. That
  is now counted and logged with the name of the code doing it, and reported as `nested_acquires`
  in health and in a diagnostics bundle. It also bounds the ingest exemption above: a durable task
  that already holds a connection still takes the deadline, because hanging there would stop ingest
  permanently and lose every later detection, where failing one acquire risks at most the event in
  hand.

- **Shutting down while a request was in flight could leave a connection open forever.** Closing
  the pool closes checked-out connections too, so a request finishing afterwards handed back one
  that was already closed. Rolling it back then failed, which is the path that treats a connection
  as corrupt and opens a replacement — putting a live connection into a pool that had just been
  closed, on every shutdown that raced a request. A closed pool now discards what it is handed.

### Changed

- **A species you have renamed is now recorded in the species catalogue, against the species rather
  than against a spelling of its name.** A rename is the one piece of naming an owner authored, and
  it lived in `taxonomy_cache` beside columns that are a cache of provider answers and can be
  refetched at will. It was keyed on a scientific name, so a taxon renamed upstream lost the name
  its owner had given it. The catalogue has held an override table since its first migration, and
  the shared naming rule already prefers it over every other source, but nothing ever wrote to it,
  which is why that precedence had to be written out again wherever a name was chosen. Renames now
  go to the catalogue, keyed on the species, and existing ones are carried over on startup. The
  copy in the detection database is still written and still read, because the pre-3.0 name-recovery
  paths consult it; the catalogue is the store of record. The migration only fills gaps, so a name
  you have since changed or cleared is never resurrected by a later startup, and a rename whose
  name resolves to no single catalogue species is counted and left where it is rather than attached
  to a guess. Owner diagnostics report how many renames the catalogue holds.

- **Removed a second, name-keyed way of reading the daily rollup that nothing used.** Species
  aggregation moved to the catalogue's stable identity, and the leaderboard and its trends now
  group on one shared key. The rollup reader that predated it stayed behind: 128 lines that grouped
  by display name, kept compiling, and kept a branch for a schema no migrated database has. Nothing
  in the application called it; it survived only because three tests used it to check that rollups
  had been written. Those tests now read the rollup table directly, which is what they were
  actually asking, so the behaviour stays covered and the duplicate reader goes.

- **A model's labels are read from the catalogue rather than its label file.** `labels.txt` is
  verified when a model is downloaded and never again, so every inference since has trusted
  whatever is on disk. The catalogue holds a row per output index carrying the same label,
  compiled from a file that was proven at install time, so that is where the labels now come from.
  It is used only when the catalogue holds a complete, contiguous set matching the model's declared
  output width: a short mapping would truncate a model's classes and a gap would shift every label
  after it onto the wrong class, so both are refused and the file is read instead. A model the
  catalogue does not know, or a catalogue that is absent or unreadable, behaves exactly as before.
  Verified against a live install: the catalogue reproduces all ten installed label files byte for
  byte, 34,746 labels in total.

- **Every model output is now recorded, including the ones nothing could identify.** An output whose
  species could not be resolved was skipped entirely, so for 707 of a 10,000-class model's outputs
  the catalogue held nothing at all, not even the label the model uses. That is what kept
  `labels.txt` load-bearing at runtime. Those rows now exist, carrying the label and an explicit
  `unknown` class. Coverage counts identified outputs rather than rows, so a model is not called
  complete merely because every index has a row: the reported figures are unchanged, except that
  two models drop by one apiece where an output explicitly declared `unknown` had been counted as
  mapped. An unknown output also reads as an unresolved gap rather than a non-species class, since
  "we cannot identify this" and "this is not a species" are different claims.

- **The daily rollup is keyed on catalogue identity like everything else.** It was the one place
  the grouping key is stored rather than recomputed, and it forms half the primary key, so it had
  been pinned to the old format to avoid a table holding two formats either side of an upgrade.
  Rebuilding it was never an option: on a real install 29 rollup rows covering 97 detections
  predate the oldest surviving detection, so the rollup is the only record of them. The keys are
  now rewritten in place, with identity resolved from detection history rather than the catalogue
  so the migration stays inside one database, and only where history is unanimous: a row matching
  more than one identity keeps a text key rather than being assigned a guess. Verified against
  that install, 193 rows and 843 detections before and after, 150 rows gaining an identity, and
  the 29 irreplaceable rows untouched.

- **Species are named from the catalogue rather than from whichever detection sorted last.**
  Grouping already keyed on catalogue identity, but the name shown for a group was still taken
  from one of its rows, so a taxon recorded under two names was counted once and then labelled
  arbitrarily. One precedence rule now decides, at read time and in one place: an owner's own
  rename first, then the catalogue's curated name for the reader's language, then English, then
  the scientific name, and only then whatever the detection already carried. Nothing is written
  back into a detection's identity, because a name in a language is a rendering and not a fact
  about the bird. On a real install this changed 3 of 42 species, each toward the IOC spelling:
  "Eurasian Blackbird" to "Common Blackbird", "Common Wood-Pigeon" to "Common Wood Pigeon", and
  "Gray-headed" to "Grey-headed". It also brings the Italian and Chinese names that the previous
  sources largely did not carry.

- **Species are counted by catalogue identity rather than by name text.** Phase 4 of the versioned
  species catalogue begins. A scientific name is not stable: when a taxon is split, lumped or
  synonymised, `Parus caeruleus` and `Cyanistes caeruleus` become two different birds to anything
  keying on the text, so a leaderboard divides and a species page shows half its sightings with
  nothing to warn anyone. Grouping now prefers the catalogue's opaque `species_id`, which does not
  move when a name does, and keeps the existing taxon and name keys underneath so a detection the
  catalogue cannot identify groups exactly as it did before. Each source is namespaced, because
  `species_id` and `taxa_id` are integers from different databases with overlapping ranges and
  would otherwise merge unrelated species. Verified against a year of real detections: the same 42
  groups before and after, with no group split and none merged. The daily rollup keeps writing
  the key format already on disk, because it persists that key and the table holds aggregate
  history whose detections no longer exist; migrating it is a separate step.

- **NumPy 2 is now supported, and the numeric contract behind it is tested.** The dependency cap
  moved from `numpy<2.0.0` to `numpy<3.0.0`, which takes the container from NumPy 1.26 to 2.x. A
  major NumPy bump can break two things quietly: the binary interface every compiled extension
  links against, and NEP 50 value-based casting, which decides whether `float32` arithmetic stays
  `float32`. Neither was covered, because the test suite mocks every inference runtime. Both are
  now covered by a contract test that runs the classifier's real probability normalisation,
  softmax, preprocessing branches and quantisation path, and exercises OpenCV across the array
  boundary. Verified byte-identical between 1.26.4 and 2.5.2 before the cap was raised.

- **eBird distances now follow your chosen unit system.** The notable-nearby scope, the species and
  detection sighting panels, and the eBird radius field render kilometres for Metric and miles for
  Imperial and British, instead of always printing km. The radius is still stored and sent to eBird
  in kilometres because that is what its API accepts, so switching units never rewrites a saved
  search radius. The unit preference is now labelled **Display Units** rather than Weather Units,
  since it no longer covers weather alone, and a public dashboard reports the radius the owner
  actually configured instead of assuming 25 km
  ([#207](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/207)).

- **Alternative frame previews now use their retained full-resolution images.** The compact 240px
  JPEGs remain limited to the filmstrip, while selecting a frame or comparing its full-frame peer
  loads the authenticated full-size candidate instead of stretching a thumbnail across the modal.

- **Finished jobs now remain newest-first before and after a browser refresh.** Active work keeps
  its queue-admission position while progress arrives, but a completion or failure is placed once
  at its terminal time instead of temporarily inheriting the older job-start time.

- **The Explorer species facet now includes every recorded species.** The desktop list uses the
  remaining viewport height and scrolls only when the complete set is taller than that space;
  smaller filter panels stay bounded and searchable ([#197](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/197)).

- **Manual identifications no longer show stale automatic-analysis warnings.** The earlier video
  evidence remains stored for diagnostics, but once an owner identifies the species the detection
  view stops presenting an inconclusive model run as if it still describes the current result.

- **Live work now stays put while it progresses.** Full-visit and best-frame jobs retain one
  timestamp from queue admission through execution, queued video work keeps that timestamp when a
  worker starts, and the browser reconciles polling with fresher live progress without moving a row
  or running a bar backwards. Work lanes, including taxonomy enrichment, use a fixed operational
  order; the job manager, combined notification timeline and global progress bar use short,
  reduced-motion-safe transform animations instead of long layout-driven width transitions.

- **Desktop snapshot choices remain selectable at the edge of the filmstrip.** The overflow fade
  is now a separate pointer-transparent layer instead of a mask on the interactive scroller. The
  selected frame uses a subtle lift, scale and shadow rather than a persistent blue outline.

- **Detection media controls no longer cover the bird name or snapshot choices on phones.** The
  title, favourite, playback and full-visit actions, and snapshot rail now form one ordered footer
  that wraps upward as a unit. Full-visit readiness is part of the play action instead of looking
  like a second play button, while the crop/full-frame comparison remains isolated at the top.

- **Detection frame choice now happens in the photograph itself.** The old full-screen crop/frame
  picker is gone. Owners can preview only genuinely retained Frigate frames from the filmstrip,
  compare them against the saved crop or full frame, then explicitly save or cancel. The strip keeps
  its edge fade, 44px controls and unsaved-state label on phones, while media actions share one
  predictable lane instead of overlapping the close control or one another.

- **Notifications and finished-job history no longer grow into an endless page.** Both views show
  20 rows at a time with 10, 20 and 50-row choices, bounded previous/next navigation on phones and
  full page controls on wider screens. Active work remains unpaginated, filters return to page one,
  and a page is clamped automatically when live history shrinks. The Job manager route now opens the
  manager rather than silently rendering the notification timeline again.

- **The detection view says what it identified above the name, not above the photograph.** The
  label sat over a row that opens with a circular reference photo, so it read as a caption for the
  picture rather than for the record. The person glyph beside it is gone: it only restated the words.

- **The crop and full-frame switch no longer collides with the favourite action on phones.** The
  view switch keeps its recovery path for tightly cropped detections, while a dedicated action lane
  gives both controls full-size touch targets without overlap.

- **The options strip no longer shows a native scrollbar** across the image gradient. The bar is
  hidden and a generous trailing-edge fade makes additional frames clear, but only while the strip
  actually overflows, so a strip that fits is not clipped for decoration.

- **The video notice stops nesting a card inside a card.** The notice is already tinted and
  bordered; its technical details added another border and background inside that, and the evidence
  list drew its own rules inside that again. One hairline separates them now.

- **The species reference and nearby sightings are part of the record**, not folded behind a
  disclosure that had to be opened every time.

- **The detection id opens as a little terminal.** The disclosure you click is the window chrome
  itself, and the id is printed as command output with a blinking caret. The window furniture
  follows the viewer's own platform, inside and out: traffic lights over a dark shell on macOS, a
  bevelled Windows 95 title bar over a black DOS box on Windows, and a GNOME close button over
  Ubuntu's aubergine with its green bash prompt on Linux. The caret stops under
  `prefers-reduced-motion`.

- **The species info button has padding.** It carried no padding class at all, so for a guest, whose
  sibling actions are hidden, it collapsed to the height of its own text.

- **The Explorer loses two sets of horizontal rules.** The timeline was wrapped in a line above and
  below, putting one directly above the first row of detections, and the pagination was wrapped the
  same way. Against a grid of cards that already carry strong edges, those read as lines drawn across
  the page rather than as structure. Both are separated by space now.

- **Mobile species tagging and notifications no longer hide controls.** The species picker follows
  the browser's visible viewport when an on-screen keyboard opens, keeps its results scrollable in
  short and landscape layouts, and exposes proper dialog and field semantics. Phone notifications
  now use a safe-area-aware lane beneath the detection close control, which remains anchored while
  detection content scrolls or the device rotates. Desktop notification placement stays unchanged.

- **The notification view is owner only.** Every job, error and process event was already hidden
  from guests, so a guest was left with a page that could never hold anything.

- **Pages no longer sit narrower than the header above them.** The page header renders only for
  signed-in owners, at the shell width, while About and the notification view constrained themselves
  to a narrower column. For an owner that read as a broken second header with mismatched edges. Both
  now take the shell width, and About drops the eyebrow that repeated the header's own title.

- **Notifications lead with the capture, like the field log.** A detection whose event is known
  shows its photograph rather than an abstract badge, in a fixed box with a placeholder underneath so
  a missing image cannot shift the row. Every other kind gets an icon for what it is: a warning for a
  failure, a clock for a job in flight, a tick for one that finished, a download for an update, a
  bird for a detection with no capture, a bell for anything else.

- **The timeline rail is drawn correctly.** Its marker was offset against the list border by hand,
  which left the dot 1.5px off the line and hanging outside the box; and because the rail column was
  a grid item, its box stopped at the row padding and the line broke between every entry. Rail and
  marker now share one centred column, the line runs unbroken, and it starts and stops at the outer
  dots instead of dangling past them.

- **The page is the width of a reading surface**, matching About, rather than stretching short rows
  across the full shell.

- **The notification view is one timeline instead of two tabs.** A job that failed is the most
  urgent thing this app can say, and it was filed under a different tab from notifications, one click
  from the place people look. Jobs, errors, birds and updates now share a single chronological river
  grouped into Now, Earlier today, Yesterday and Older, filtered by chips that state their size
  before they are applied. The job manager stays reachable for the controls a timeline cannot carry.

- **The timeline reads real job status.** Active and recent jobs from both local progress and the
  authoritative server snapshot are merged with matching notifications, so failed jobs actually
  appear under Errors without duplicate progress rows. Calendar grouping also follows local-day
  boundaries across daylight-saving changes.

- **Amber went back to meaning one thing.** Progress bars ran a gradient from the attention colour
  through brand into sky, spending the one colour reserved for "this needs a person" on the thing you
  can safely ignore. A job in flight is brand blue; only a failure is amber.

- **Opening a notification is a real control.** It was a paragraph styled to look like an action,
  which could not be focused or clicked.

- **Owner-only filters are hidden rather than shown returning zero**, and a filter left selected as
  access changes falls back instead of stranding a guest on an empty list.

- **The empty page says what will fill it** and offers the field log, rather than reporting that it
  holds nothing across an otherwise blank screen.

- **Update notifications now converge within minutes instead of potentially remaining stale for
  half a day.** The telemetry version endpoint reads CI's promoted D1 row without an isolate-local
  stale copy, the backend uses a bounded fifteen-minute success cache with a five-minute failure retry,
  and browser/proxy caching is disabled for the instance status response. The shared UI store now
  retries failed checks and refreshes while visible, on navigation, and after returning to the tab;
  version-keyed dismissals remain honoured.

- **Anonymous telemetry now has an explicit Free-tier and privacy boundary.** D1 schema updates use
  ordered, non-destructive migrations; new heartbeats retain only a hashed installation identity;
  exact health replays no longer spend the daily write budget; scheduled bounded retention removes
  stale history and legacy raw identifiers; and disabling both telemetry options requests deletion
  before rotating the local identity. Public telemetry hides cohorts below three installations and
  computes selected-window health signals from accepted batches rather than lifetime counters.
  Workers Logs are sampled at 10%, tracing remains off, and the 40,000-unit application write cap
  preserves headroom beneath Cloudflare's Free-plan D1 limits.

- **Detection details and dashboard:** On phones, the favourite action no longer covers the Best crop /
  Full frame switch. Location-level eBird notable reports now live beneath the dashboard Field log
  instead of appearing on every detection, with honest disabled, loading, empty, error, and scoped
  result states.

- **About:** The owner instance card now stays within the phone viewport when the issue-report
  fingerprint contains a long model identifier. The availability strip shrinks with its card,
  while the fingerprint wraps above a full-width Copy action on narrow screens.

- **Dependencies:** Reviewed and consolidated the outstanding runtime, UI, telemetry Worker, and
  workflow dependency updates against current `dev`. The OpenVINO floor is consistent across both
  Intel-capable image flavours, CPU ONNX Runtime 1.28 is covered across CPU/Intel/ARM64 paths while
  the CUDA compatibility ceiling remains unchanged, and the markdown-it 15 migration preserves
  existing bare-domain links while using its bundled TypeScript declarations. The telemetry test
  toolchain also overrides its vulnerable transitive Undici range to the patched 7.29 release.

- **Ten more bird facts in the footer ticker**, weighted towards birds that turn up at feeders.
  Broad claims were narrowed to the species, measurement or observation the research supports,
  including chickadee cache recovery after 28 days and the British record of 61 wrens roosting
  together.

- **Corrected several bird myths and overstatements.** Woodpecker skulls work as stiff hammers, not
  shock absorbers; geese have serrated bills rather than teeth; penguins use pebbles as nest
  material rather than marriage proposals; and flocking starlings respond to around seven nearby
  neighbours rather than tracking exactly seven birds.

- **The footer signature drops the sentiment.** "Built with AI assistance for the love of bird
  watching" becomes "Built with AI assistance, and a lot of trial and error", and the string moves
  from `about.built_with_ai` to `footer.built_with_ai`, which is where it is actually used.

- **The footer ticker is stable and safe on narrow screens.** Its mobile layout reserves enough
  room for the bundled translations, skips missing or single-item fact lists safely, clears both
  timers on teardown, and changes facts without fading when reduced motion is requested.

- **The About page speaks in the first person again.** The project description had been written
  as third-party marketing copy about the author ("YA-WAMF is a personal project started to
  experiment with AI-assisted coding"), which is the README's own sentence with the "I" removed,
  and it read like a brochure. It now matches the README's voice. "How It Works" loses its title
  case, the credits line about AI assistants matches the grammar of the lines around it, and the
  Flaticon credit is no longer punctuated with a stray hyphen.

- **The pipeline shows which way the data moves.** A soft pulse sweeps each step in turn, in the
  order a detection actually travels, with the border blooming as it passes. One sweep per nine
  seconds and then a rest, so the page is still while you read it. Off entirely under
  `prefers-reduced-motion`.

- **Steps that were never probed say so.** MQTT and the database had no status chip at all while
  every neighbour had one, which left the row looking ragged and the gap looking like a fault.
  Both now read "not checked", which is the honest label for a step with no health endpoint.

- **The availability strip now explains its state.** It keeps a stable footprint while its request
  loads or cannot be read, and distinguishes those states from a successful window with no measured
  history. It also labels which end is now and shows the availability percentage returned by the API.

- **A step that cannot be read no longer says "unknown" twice**, once in the chip and again in the
  detail line directly beneath it. The detail line now says there is no reading from here.

- **The external link arrows in Reference and thanks** were a bare "↗" character sized by the
  display font, which rendered them far larger than their labels. They are a properly sized icon now.

- **The leaderboard opens with the bird, not a repeat of the table.** The most detected species of
  the selected period is shown through representative visits from your feeder, captioned "Most
  detected this month" and following the Day, Week, Month and Total control. Simultaneous visits on
  different cameras stay distinct, while consecutive frames from one visit contribute only their
  clearest photograph. Where more photographs exist than tiles, they cycle slowly; a single
  photograph is shown as one frame rather than a grid with gaps. Broken snapshots disappear without
  leaving a blank tile, and every transition stops for anyone who prefers reduced motion. Heard-only
  leaders use the ranking instead because an audio detection cannot provide a feeder photograph.

- **The rebuilt UI now carries its evidence and privacy boundaries end to end.** Explorer facet
  counts use the same history window as the guest event list, clicking a frame in a visit opens
  that frame, and the review queue only offers a crop/full-frame comparison when both images come
  from the same clip moment. BirdNET failures are shown as unavailable rather than zero activity,
  audio-only periods remain visible, thumbnail controls meet the touch-target standard, and custom
  date inputs have distinct accessible names.

- **The classifier's status notice stops competing with the identification.** "Identification
  unchanged" and its error details were the second thing read on the panel, above the facts. The
  notice is now a quieter note below them, where an explanation belongs, and the caption over the
  photograph gained a deeper scrim so it stays legible now the image fills its panel.

- **The detection actions say what they do.** "Manual Tag" is now "Pick a different species", and a
  detection the model named can be accepted outright with "Confirm Coal Tit", which marks it as
  human-verified in one press instead of reopening a species picker to choose the name it already
  has. Confirmation applies the server's canonical names, preserves an existing behaviour analysis
  when the identification did not change, and reports confirmation rather than reclassification.
  The action is not offered for detections already confirmed, or for ones with no species to confirm.

- **The detection view shows the evidence this install actually has.** Ranked snapshot options run
  along the bottom of the photograph for owners and open with the chosen option selected. They are
  labelled as snapshot options rather than as the frames that produced the identification. Each fact
  row carries an icon, and the identification header states whether the name came from the model or
  from you. BirdNET reports a late match, loading, unavailable and measured no-match states honestly;
  a disabled integration has no row. Frigate's percentage is labelled as a bird-detection score, not
  species agreement.

- **Detection details leads with the detection.** The species text, the eBird map and the notable
  nearby list, which together were the largest thing on the panel and were about other people's
  sightings, now sit behind one disclosure. The media panel fills its column when the same moment has
  a full-frame counterpart; otherwise it preserves the complete stored image rather than cropping it
  without an escape hatch. Reference photographs retain their footprint when the provider image fails.

- **Explorer replaces five rows of controls with a filter bar and counted facets.** Three stacked
  selects, three buttons, a page-size picker and a pagination row above the grid are now a single
  line stating the result count, with applied filters shown as removable tokens and the rest behind
  a Filters button that opens only when wanted. On a phone this removed roughly 1,290 pixels of
  chrome that sat between opening the page and seeing the first photograph.

- **Every Explorer filter states how many results it would return.** `GET /api/events/filters` now
  reports a detection count per species, per camera, and for favourites, audio matches and video
  analysed, so an option that would return nothing says so before it is chosen. Species counts are
  taken over the same canonical grouping the options are built from, so name variants of one species
  count once.

- **The dashboard is now a field desk: one chronological log of the day with the outstanding work
  docked beside it.** Repeat frames of the same bird on the same camera within ten minutes fold
  into a single visit row showing the clearest frame and the best score, so one blackbird landing
  once no longer prints four cards. The full-height latest-detection hero and the four-metric
  overview ribbon are replaced by a compact day bar (visits, species, unresolved, calls heard,
  cross-confirmed) and a **Needs your call** queue listing detections that fell below the naming
  threshold, oldest first, with Identify available inline on the row. New context cards cover
  per-camera visit counts with online status, an audio-versus-camera reconciliation that is honest
  when the two sensors never corroborate each other, and the temperature range visits happened in.
  The day bar, log, queue and cards all describe the same 24-hour window, so the numbers cannot
  contradict one another.

- **Small captures now open on hover and on keyboard focus.** Any thumbnail in the log expands to
  a preview panel with the full frame, score, camera, time and conditions, modelled on the existing
  header camera popover: it stays open while the pointer travels into it, dismisses with Escape,
  reuses the thumbnail already fetched rather than a second request, and honours reduced-motion.

- **Adding an observation now shows the evidence at the size you need to judge it.** The review
  step is media-led: the frame takes the larger half of the screen, and when the classifier scored
  a crop you can switch between that exact input and your original upload to tell a bad crop from
  a bad classification. The model, provider, scored input and original filename are listed as
  evidence rather than left implied by a single badge, and the confirm button names the species
  it is about to add instead of saying "Add observation".

- **The About page now shows what this instance is actually doing.** The eight-step description
  of the pipeline is replaced by the same seven steps annotated with live state: cameras online,
  which classifier is loaded and on which provider, whether BirdNET-Go correlation and
  notifications are configured, and whether the browser is receiving live updates. A step whose
  status cannot be read says "unknown" rather than claiming to be healthy, and steps with no
  status source (the broker, the database) say "not checked". Two new columns state what is
  stored in each table and which outbound calls are enabled, so the privacy answer lives on the
  page rather than across three documents.

- **The About page is now the page, not a brochure.** The eighteen-item feature grid, the
  technology-stack card, the jump-to nav and the separate resources card are gone. What remains is
  what the page is for: what this is, how it works with live state on every step, what it stores
  and sends, the build detail to quote in an issue report, and the credits. The feature list stays
  documented in the readme and docs.

- **Adding an observation gives the evidence the room.** The gradient intro banner and the 16rem
  step rail are replaced by a slim bar carrying the filename, the flow status and Start over, so
  the frame and the candidate list get the width instead of the chrome.

- **"Work through the queue" now opens a walk-through instead of sending you to Explorer.** A
  distinct full-screen flow takes the unresolved detections one at a time: the frame at full size
  with its time, camera, score and conditions, and a decision rail offering the species this feeder
  actually sees, most frequent first, rather than the alphabetical head of an eleven thousand label
  list. Each item can be identified, hidden as not a bird, skipped for later, or opened in full. It
  states position and what is left throughout, and closes on an honest summary of what was decided
  and what was skipped. Where a snapshot scan has already found the crop the classifier scored,
  the walk-through opens on that crop with a Best crop / Full frame toggle, since a wide feeder
  shot rarely settles what a low-confidence blur is. Detections without a stored crop say so
  instead of pretending the full frame is one.

- **About shows how long this instance has been running.** The readiness probe already records
  when the process started, so "This instance" now states uptime and the time it started, with no
  new endpoint. The colophon is no longer boxed in a card, since it reads as the page opening
  rather than as one panel among several.

- **Uptime is now recorded, so About can show it honestly.** The application writes a heartbeat
  every five minutes to a new `health_samples` table, and `GET /api/stats/uptime` turns those rows
  into an availability window. About draws the last 24 hours as a strip and names the longest gap,
  for example "47 minutes missing at 05:40". A bucket with no heartbeat is reported as down, and a
  bucket from before the first heartbeat ever recorded is reported as unknown rather than as an
  outage, so a fresh install does not claim a day of downtime. Heartbeats are pruned after seven
  days.

- **Dashboard and About polish against the agreed designs.** The field log now draws a spine
  behind the state dots, so the day reads as one thread rather than a stack of unrelated rows, and
  it says how many earlier visits are not shown instead of stopping silently at twelve. Camera rows
  keep the count and its unit together and carry the last visit time, so a quiet camera is visibly
  quiet. About states whether the build is up to date, using the update check that already exists.

### Fixed

- **Model outputs naming a superseded genus had no catalogue identity, because the mappings were
  compiled against a seed with no synonyms in it.** The seed builder takes the Catalogue of Life
  bird synonyms, and the runtime catalogue has carried them since they were added, but the script
  that compiles the model output mappings never passed them. So `Accipiter gentilis` resolved
  perfectly well at runtime and was recorded as an unmapped output of a model that names it on the
  tin. Compiling with the synonyms gives 131 label-file outputs the identity they always had, 175
  once the models sharing a label file are counted separately: `Accipiter gentilis` to
  `Astur gentilis`, `Haliaeetus leucogaster` to `Icthyophaga leucogaster`, `Amazilia beryllina` to
  `Saucerottia beryllina`. Mapped coverage goes from 21,650 to 21,781 of 23,332 outputs. Verified
  against the committed mappings and against a copy of a live catalogue: no output changed from one
  species to another, none lost an identity, and no label text changed.

- **A bird could be recorded as the wrong species because the taxonomy lookup took whatever ranked
  first.** iNaturalist's `/v1/taxa?q=` is a search, not a lookup: it ranks by relevance and matches
  synonyms, so the species asked about is not reliably the first result. The lookup asked for a
  single result and took it without checking it was the name it had asked for. Measured against the
  live API with 45 real labels from the flagship model, 3 were wrong: `Buteo buteo` resolved to the
  subfamily `Buteoninae`, `Clanga clanga` to the genus `Clanga`, and `Circus cyaneus` (Hen Harrier)
  to `Circus hudsonius`, the Northern Harrier of North America, because the two were split and the
  older name still matches. A live install had recorded a Goldcrest as a Ruby-crowned Kinglet for
  the same reason. The lookup now asks for a page of candidates and takes only one whose matched
  term, scientific name, or English common name is exactly what was asked for; a genuine rename
  still resolves, because a model trained on `Regulus calendula` asks for that name and the taxon
  now called `Corthylio calendula` reports matching on precisely it. When nothing on the page is
  the name asked for, the bundled reference answers and the model's own label stands, rather than a
  different species being written into history.

- **Filtering the events list by species is no longer dominated by a taxonomy join.** A user
  reported the species filter being noticeably slower than the date and camera filters. The join
  onto `taxonomy_cache` was the cause: its conditions are ORs across different columns wrapped in
  `LOWER(...)`, a shape no index can serve, so the whole cache was scanned once per detection row
  and the join forced a `DISTINCT` over every selected column on top. The join only ever resolved a
  detection whose own scientific name is absent, through its display name, and the alias resolver
  already produces those names. Measured on a 96,118 row database across five species, total time
  falls from 541ms to 310ms and the worst case from 247ms to 63ms; two already-fast lookups get
  slower by roughly 15ms, because resolving the identity up front costs more than the join saved
  where the join was cheap. The join is kept for a `taxa_id` filter, which still reads the cached
  taxon id for a detection that has none of its own. Result sets are unchanged, checked across all
  85 names the data holds.

- **An existing install now gets the model output rows it was missing.** An artifact's mapping
  digest is computed over the whole source mapping, including outputs nothing could resolve, while
  the rows actually stored were a filtered subset of it. A live catalogue could therefore hold
  9,293 rows for a 10,000-output model under a digest asserting the mapping was complete, and the
  importer skipped the artifact because the digests matched. Recording every output reached fresh
  installs only. A matching digest means the source mapping is identical, so a row the catalogue
  lacks is absent rather than different: those rows are now added, including when the release
  itself is already held, because completing a mapping is a repair rather than an import. A row
  that would *change* is still refused, since that is a correction and needs its own supersession
  policy. On a live catalogue this added 2,434 rows across ten artifacts, left every existing row
  untouched, and left coverage reporting unchanged.

- **A bird that has been renamed no longer counts twice.** The catalogue takes bird names from the
  IOC World Bird List, whose multilingual export carries one curated name per species per language
  and no taxonomic history, so nothing recorded that a species had been called something else. On a
  live install that showed as the Eurasian Jackdaw appearing twice in the audio list: BirdNET-Go
  reports `Corvus monedula`, IOC 14.2 calls that bird `Coloeus monedula` after the jackdaw genus
  split, and with no synonym recorded they were two birds. The catalogue now carries 7,256 bird
  synonyms taken from the same pinned Catalogue of Life release that already supplies non-bird
  taxonomy, verified against its recorded checksum. IOC keeps ownership of names; Catalogue of Life
  supplies only the crosswalk. No API key and no network at runtime.

- **A newer shipped catalogue now reaches an install that already has one.** The catalogue is only
  copied from the shipped seed on a genuinely fresh install, because a live one may hold owner
  renames and imported releases. That meant a newer catalogue never arrived anywhere else, and the
  release importer built for exactly that was never called. The shipped seed is now offered as a
  release at startup: idempotent, transactional, verified against its own digest and foreign keys,
  never fatal, and reported. Measured against a copy of a live catalogue, it matched all 19,141
  existing species without adding one, and left owner overrides untouched.

- **Deep Video Analysis names the model again.** The card that reports a video classification
  sometimes showed no model at all, which reads as though none was involved. Two causes, both real.
  A snapshot fallback ranked its results through a helper that carries no provenance, so no model
  was ever recorded: on a live install 11 completed classifications had none, every one from a
  snapshot source. Separately, a regional model is addressed as `parent/region` and region variants
  are nested under a parent that owns the id, so an exact lookup found nothing and anyone running a
  regional model saw no name. Regional models now read as "Small Birds (EU)", and a model the
  registry no longer publishes reports its id rather than disappearing. Reported in #257.

- **Filtering the events list by a species is faster.** A user reported that the species filter was
  noticeably slower than the date and camera filters, which are effectively instant. Measured on a
  96,108 row copy of a real database it took 26ms, and the plan showed the taxonomy join scanning
  once per detection row because a predicate wrapped in `LOWER()` cannot use an ordinary index.
  Indexes matching those expressions are now in place. The catalogue identity introduced with
  species grouping is also resolved to concrete ids before the query is built rather than left as a
  subquery over the whole table, which had taken the same filter to 41ms; it is now 29ms end to
  end. The remaining cost is the taxonomy join itself and is not addressed here.

- **An expired Frigate event is no longer reported as a warning on every page load.** Frigate
  retires events long before YA-WAMF retires detections, so an older detection's upstream event is
  gone for good. The events list checks media availability for every row it renders, and logged a
  warning each time it found one missing: 958 log lines in 22 hours from 29 events on a reference
  deployment, for a condition that is expected, permanent and needs nobody. Real warnings were
  buried underneath. The condition is now stated once per event per window, at info, in words that
  say what it means for the detection. Frigate is still asked every time, so a restored event or a
  transient failure during a Frigate restart is never answered from stale memory.

- **Success and "needs your attention" are no longer the same colour.** The shipped Blue Tit theme
  paints the secondary accent amber, and success states were built on that accent, so a passed
  check and a warning rendered identically. In the shared diagnostic dialog the two sat in the
  same expression: a `passed` step and a `warning` step both came out amber, which removed the
  distinction the dialog exists to draw. Confirmed, passed, healthy, connected and verified states
  now use a dedicated semantic green that no theme can repaint, while amber goes back to meaning
  only "this needs a person". Affects the Frigate, MQTT, notification and model test flows, the
  first-run wizard, integration status, and success badges throughout. Reported in #243.

- **A plumage label can no longer be recorded as a scientific name.** The label grammar is now
  declared per model artifact in the registry instead of inferred from each line's shape. The
  NABirds label files carry entries like `Lesser Goldfinch (Female/juvenile)`, which wear the same
  `Scientific (Common)` shape as the Coral labels, so the automatic taxon map recorded common names
  as scientific names for the North American regional models. Those labels now resolve through the
  bundled reference instead, and crop-detector class lists (where COCO's `kite` could have met the
  same fate) are excluded from species mapping and name enrichment entirely.

- **Portuguese installations were getting English bird names from eBird.** eBird publishes its
  locale codes with underscores and has no plain `pt`, so the regional fallback could never match
  and every Portuguese lookup quietly resolved to English. Chinese resolved to a variant carrying a
  quarter of the translated names of the one it should have used. Both now resolve correctly, and
  an explicit regional choice such as `zh_HK` is still honoured.

- **Guest sessions no longer poll owner-only endpoints into a wall of 403s.** A public visit
  repeated requests for `/api/settings` and camera status that the backend always refuses, filling
  the browser console and the server log with expected failures. Settings refresh and both camera
  status readers now wait for owner access, and the About pipeline tells guests a reading is
  `owner only` instead of showing an `unknown` that reads as a fault in a healthy install. The
  notifications step gets the same honesty: a guest sees `owner only` rather than a guessed `off`.

- **Leaderboard trends no longer shout percentages against a baseline of one.** A species moving
  from 1 visit to 93 rendered `+92 (9200.0%)`. The percentage now only appears when the previous
  window is big enough to compare against and the ratio stays in a readable range; the count
  keeps carrying the trend on its own everywhere else. Average confidence in the rankings joins
  every other confidence in the app as a percentage, and the sunrise and sunset windows next to
  the weather overlays now say which is which.

- **Field log rows keep the species name whole at desktop widths.** A visit with several frames
  was truncating names as short as "House Sparrow" while free space sat elsewhere in the row. The
  thumbnail stack now shows two frames and counts the rest; the name is the primary reading of
  the row. On the leaderboard hero, the kicker line carries its own scrim so it stays legible
  when a bright collage slice sits behind it on short mobile cards.

- **The About page now lists every browser-side call the sighting map makes.** The eBird map
  fetches OpenStreetMap tiles from each viewer's browser, which belongs in the "What leaves your
  network" panel next to the eBird lookup itself; both rows appear when eBird sightings are
  enabled, and the panel keeps its promise that nothing unlisted leaves the network.

- **The Health page no longer calls normal filtering a degraded pipeline.** Any dropped event at
  all, including a detection correctly rejected by the confidence threshold or a blocklist, flipped
  the Event Pipeline card to `DEGRADED` while the backend reported the pipeline healthy on the same
  screen. Drops are now classified where they are recorded: expected, configuration-driven filtering
  stays out of the health verdict, and only a drop caused by a fault degrades the card. Filtering
  gets its own **Filtered Detections** card showing how much each rule rejected and the species and
  confidence of the most recent ones, so the number stays visible without being dressed up as a
  failure.

- **Recent Backend Diagnostics now shows what it says it shows.** The list is headed "warnings and
  errors" but was also carrying every expected filter drop at `info` severity, so eight low-confidence
  rejections could push a real failure out of view.

- **The responsive Events species filter now honours the configured naming preference**
  ([#180](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/180)). Filter values remain
  canonical, while their visible labels use the same common/scientific-name pairing as detection
  cards instead of exposing only the model's scientific label.

- **The leaderboard stops printing a percentage it cannot stand behind.** Every camera trend read
  "+76 (0.0%)" because the previous window holds no camera data to compare against, so the figure was
  the same on every row and meant nothing. A trend now shows its percentage only when there is a
  previous window to measure against, and each mode is asked about its own history. Heard counts keep
  their real percentages, combined trends use the combined previous count, and camera counts show the
  change alone when that is the only supported comparison. Rising and Most recent remain when they
  describe a different species from the leader, and use the selected Seen, Heard, or Both evidence.

- **Review confirmations now persist and leave the queue immediately.** Choosing the species a
  detection already shows, including a translated alias of the same taxon, records the human
  confirmation without rewriting its canonical taxonomy or adding false correction feedback. The
  API and dashboard synchronise `manual_tagged` immediately instead of depending on a later live
  update.

- **Dashboard review and camera state now follows saved settings.** The review queue uses the
  configured classification threshold instead of a fixed 60% floor. The camera section shows only
  selected cameras when a selection exists, keeps configured cameras with unavailable health as
  unknown, and counts grouped visits rather than raw Frigate frames.

- **Active video workers no longer time out while reporting progress.** Every valid worker protocol
  event now refreshes liveness, so a long frame-analysis run is not killed merely because a heartbeat
  and a progress event crossed. Manual and maintenance jobs recover from a genuine worker failure by
  using the existing snapshot fallback and retain a diagnostic record of the recovery.

- **Every frame in a visit previews itself.** Hovering any thumbnail in a folded group showed the
  same clearest frame. Each thumbnail is now its own trigger with its own preview, stating which
  frame it is, and clicking one opens that frame rather than the visit's best.

- **Explorer puts the facets beside the results.** They were hidden behind a Filters button and
  opened full width above the grid, which is not the layout that was chosen: the facet rail is now
  persistent alongside the photographs on desktop, and collapses behind the button only where there
  is no room for it.

- **The field log fits a phone.** Rows were around 225 pixels tall because the action button sat on
  its own line with nothing beside it, so four visits filled a screen. The action now shares the row,
  the score and camera appear under the species name instead of being hidden, and the thumbnail
  stack shows one frame rather than three, which stops long species names truncating. Eight visits
  now fit where four did. The day bar keeps its live indicator inline, and "See full history" stays
  on the heading row.

- **The review queue is owner only.** "Needs your call", its walk-through, and the Identify action
  on a flagged row were visible on an unauthenticated dashboard, where the identify and hide calls
  they offer are refused. They are now gated on owner access, so a guest sees the day without being
  offered work it cannot do.

- **Top Visitors is readable on the dashboard again.** It lays out horizontally and was being
  compressed into the context rail on desktop. It now sits full width below the desk, where it
  was before, with a layout test to keep it there.

- **Leaderboard rows now recover common names already present in the taxonomy cache.** Historic
  detections that predated successful taxonomy enrichment no longer remain scientific-name-only in
  the rolling or all-time rankings. Cached taxonomy identifiers, provider names, and durable manual
  overrides are applied locally without adding external requests to the leaderboard path.

- **Manual observation uploads now pass through the bundled Nginx proxies at their documented
  limits.** The exact upload route accepts a bounded 256 MiB multipart request and streams it to
  the backend, which continues to enforce the 25 MiB image and 250 MiB video file limits. The
  browser rejects oversized files before upload, and container smoke tests cover requests larger
  than Nginx's former 1 MiB default.

- **Public readiness checks now report backend readiness instead of returning the web app.** Both
  monolithic and split frontend proxies route the exact `/ready` path to the backend without
  caching it. Container health and image smoke tests now exercise that public route, so a future
  proxy regression cannot be hidden by checking the backend port directly.

- **Full-visit clips no longer become permanently short when Frigate is still finalizing a recording.**
  Automatic generation waits for the requested window to settle, measures the downloaded duration,
  and makes bounded attempts to upgrade a partial result. Recording files are staged and replaced
  atomically only when the candidate is longer, while the player labels a retained usable fallback
  as a **Partial visit** instead of presenting it as complete.

- **The Events page no longer lets taxonomy aliases or slow Frigate media checks hold up a page.**
  Unfiltered reads avoid the taxonomy join, filtered reads deduplicate detections that have more
  than one cached alias, and clip availability checks use a bounded two-second request window with
  controlled concurrency instead of allowing one page to wait on repeated long timeouts.

- **Owners can set a durable common name without losing the provider's taxonomy value.** Detection
  details now offer an owner-only common-name editor and reset action. The override applies to
  existing sightings immediately, remains authoritative across taxonomy refreshes and localized
  lookups, and can be cleared to restore the latest provider name.

- **BirdNET enablement, source mapping, and species confirmation now use strict runtime semantics.**
  Disabling BirdNET removes its MQTT subscription and a live toggle reconnects before another audio
  message is ingested. A named camera with no source mapping matches nothing; only an explicit `*`
  is a wildcard. Initial correlation searches for the visually classified species before retaining
  a higher-confidence different call as context, and same-species audio that arrives later is
  presented as confirmed in detection details with its score, spectrogram, and clip.

- **Authentication tokens no longer appear in monolithic container access logs.** Nginx now logs
  the request path without its query string, the duplicate Uvicorn access log is disabled, and the
  recommended Compose deployment rotates JSON logs at 10 MB while retaining three files.

- **Automatic database migration backups no longer grow without a limit.** YA-WAMF keeps the 10
  newest timestamped restore points by default and removes older automatic backups only after a
  new backup succeeds. `DB_PRE_MIGRATION_BACKUP_RETENTION` can raise that limit, at least one
  restore point is always kept, and manual backups are unaffected.

- **A detection no longer claims nothing was heard when audio was heard on an unmapped
  microphone.** The audio panel distinguishes a silent window from audio excluded by the
  camera-to-audio-source mapping. The established array response remains compatible with existing
  API clients, while a response header carries the suppressed count for newer clients.

- **Taxonomy retries now replace stale negative aliases cleanly.** When a previously unresolved
  common name later resolves to a different canonical scientific name, the obsolete negative row
  is removed so it cannot shadow the successful result or trigger an iNaturalist request every
  time. Malformed successful responses are treated as provider failures rather than escaping into
  request and ingest paths as unexpected exceptions.

- **A species recorded as unknown to iNaturalist is checked again instead of staying unknown
  forever.** A single lookup that found nothing was trusted permanently, so a species that was
  temporarily unresolvable never regained its common name. Those entries are now re-tested after a
  week (`TAXONOMY_NOT_FOUND_RETRY_SECONDS`), which also repairs installations already carrying one.
  Species that resolved successfully are unaffected, however old the entry.

- **A species no longer loses its common name because a taxonomy lookup failed once.** A timeout,
  rate limit, or other failure reaching iNaturalist was recorded as "no such species" and cached,
  so the species kept showing its scientific name alone. Only an answer from iNaturalist that
  genuinely holds no match is cached now; a failed request is left for the next attempt.

- **The species picker no longer lists the same species twice.** Blocking a species could show two
  identical rows, both marked as already added, when a taxonomy id resolved for the classifier
  label but not the stored detection label. Matching species are now merged on their scientific
  name, keeping whichever record carries the richer taxonomy.

- **Species in the Events filter no longer show "No events yet".** When a detection stored a
  scientific name but no taxonomy id, the filter list resolved an id live and offered it as the
  filter value. No stored row carried that id, so selecting the species matched nothing and the
  page reported zero events for a species that plainly had some. The filter now offers a value the
  events query can actually match.

- **Diagnostics no longer report a crop-detector fallback that did not happen.** Choosing the
  accurate detector tier falls back to the fast detector, but the reported reason stayed
  `fallback_fast` even when that fallback was itself missing, contradicting the `installed`,
  `healthy`, and `enabled_for_runtime` fields reported beside it. The reason now reports
  `not_installed` or `config_missing` whenever the resolved detector cannot run. Per-model crop
  policy is unchanged.

- **Short visits no longer produce a second, futile classification attempt when the event ends.**
  An event whose classification ran and was deliberately rejected by the confidence or label filter
  is now remembered as decided, so the terminal `end` recovery no longer mistakes "no detection was
  saved" for "the initial ingest failed". Previously such events were reclassified against a
  snapshot Frigate had already discarded, which always failed and logged a misleading
  "snapshot unavailable after retry" drop. Recovery of genuinely un-ingested events is unchanged.

## [2.17.0] - 2026-08-01

### Added

- **Owners can add a verified observation from an uploaded photo or video.** The new full-page
  **Observe → Add observation** flow securely persists the original media, runs the production
  full-frame/crop or temporal-consensus classifier path, shows alternatives and model/provider/input
  provenance, and creates a detection only after species confirmation. Durable progress survives
  browser reloads, failures retry without re-uploading, duplicate content is rejected, and locally
  stored media remains available to the normal snapshot and clip views independently of Frigate retention.

- **Pull requests and roadmap work now have an explicit delivery contract.**
  Everyday changes use short-lived branches and reviewed pull requests into
  `dev`, while release pull requests alone target `main`. The roadmap records
  prioritised outcomes and evidence gates; issues retain actionable discussion,
  and pull requests retain the verified delivery slice.
- **CI now scans the repository's full history for committed secrets.** Gitleaks
  runs on pull requests, pushes to `dev` and `main`, a weekly schedule, and
  manual dispatch with read-only repository permissions.
- **Provider support now has a global candidate contract and an installation proof.** Registry and
  release-sidecar generator metadata distinguish providers that are safe everywhere from reviewed
  candidates that are worth probing. Compatibility evidence schema 4 binds each passing provider
  to the image flavour, inference package versions, kernel/visible accelerator identity, and model
  artifact checksum, so a runtime upgrade, host move, image switch, or replaced artifact cannot
  inherit an unrelated GPU/NPU pass.

### Changed

- **Video consensus now pools sparse, independent moments.** A fleeting bird no longer needs to
  occupy a fixed fraction of an entire retained visit. Observations less than 250 ms apart collapse
  into one moment; each source needs three independent evaluations, at least two confident votes,
  and a 60% winner among those votes. Accepted confidence is the median of at most the five
  strongest supporting moments, while cross-source disagreement still causes an abstention.
- **Accelerator selection is now ordered per model and installation.** A compatibility sweep keeps
  per-provider latency and numerical-agreement evidence; `Auto`, Settings, Model Manager, and the
  setup wizard use that measured order. The UI exposes only the image-packaged, host-visible,
  model-approved intersection, while raw settings and model-activation APIs enforce the same gate.
  Activating another model resets an explicit provider from the previous model unless the new
  model has current evidence.
- **ConvNeXt Large treats Intel GPU as host-gated rather than globally broken or globally safe.**
  The reviewed global registry allows an isolated Intel GPU probe while retaining CPU, CUDA,
  OpenVINO CPU, and Intel NPU as the safe baseline. Quark's current OpenVINO stack matched CPU
  top-1 on 24/24 real images with 4.96/5 mean top-5 overlap; older OpenVINO 2025.4.1 evidence remains
  documented as incompatible and cannot authorize a current install.
- **The global candidate registry now reflects the complete current Intel hardware audit.**
  Quark's 28 July schema-4 sweep tested the then-current 12 classifiers and both crop detectors
  over 24 real images plus detector hard negatives. Explicit regional reruns corrected the family
  attribution: Small Birds EU and Medium Birds NA expose Intel NPU as host-gated candidates, while
  Medium Birds EU failed CPU-equivalence and Small Birds NA remains excluded after inconsistent
  NPU results. The audit also adds a host-gated Intel GPU candidate for EVA-02 Large and records
  the final compatibility evidence for the subsequently retired comparison models.
  It also moves Intel GPU routes with conflicting historical results—Small Birds EU/NA, Medium
  Birds NA, FlexiViT, and RoPE—from globally safe to host-gated. Medium Birds EU and FocalNet-B
  remain globally GPU-supported because both older and current reference runtimes agree.
- **A retired saved classifier now moves to a supported model before background work starts.**
  YA-WAMF prefers an already installed ConvNeXt Large and otherwise uses the bundled MobileNet
  fallback, resets provider selection only when the active model changes, and leaves every retired
  model file untouched for rollback.

### Removed

- **Four redundant comparison classifiers no longer appear or run in current YA-WAMF releases.**
  MogaNet-S EU, ConvNeXt-V1 Tiny EU, RegNet-Y-8G EU, and UniFormer-S EU have been removed from the
  current registry, Model Manager, setup wizard, validation sweep, download path, and activation
  path. Their existing GitHub release assets remain available to pre-3.0 applications until the
  planned 3.0 asset retirement.

### Fixed

- **The weekly secret scan now acknowledges six reviewed historical findings.** Five exact
  fingerprints belong to documentation-only authorization examples, while the sixth belongs to
  an MQTT credential removed in February 2026 and subsequently rotated. New or changed findings
  continue to fail Gitleaks.
- **Manual reclassification no longer rejects good fleeting sightings or applies unsafe weak
  replacements.** Retained recordings use Frigate boxes only at timestamps backed by `path_data`,
  so one stale box cannot repeatedly classify background after the bird has moved. A video
  abstention or below-threshold candidate falls back to the best retained snapshot, while an
  explicit click no longer bypasses the configured threshold or downgrades an existing identity.
- **Reclassification evidence now describes the actual vote.** Version 3 diagnostics separate
  decoded frames, independent moments, confident candidates, and all-score observations; the UI
  reports leading-species support and the actual matching requirement in all nine language
  catalogs. Historical version 1 and 2 summaries remain readable.
- **Deep video analysis now uses sparse crops and tracked motion honestly.** Dynamic crop consensus
  counts only moments where the detector produced a usable crop and can win from three separated
  moments without requiring the bird to fill a percentage of a long visit. Frigate path coordinates
  are aligned to cached recording and event-clip timestamps so the guided crop follows the bird
  instead of reusing one final box. The centre-weighted sampler no longer fills overlapping targets
  with adjacent opening frames, and conservative cross-source agreement still rejects confidently
  wrong outliers.
- **A video abstention now explains the evidence it rejected.** YA-WAMF stores a bounded per-source
  summary with decoded, confident, required, and recurring-candidate frame counts. Detection details
  presents that evidence after reload or restart instead of reducing every safe abstention to the
  generic `video_no_results` message; all nine language catalogs include the new surface.
- **Manual reclassification now ends with an explicit outcome.** When no species clears the
  confidence and agreement rules, the progress overlay says that the identification was unchanged,
  explains why, and shows the strongest frame evidence instead of ending ambiguously at 100% with
  an empty result. Queued video and snapshot-fallback completions now carry a structured success,
  no-result, or failure outcome so Jobs, notifications, detection details, and the overlay agree.

- **Uploaded observations now retain complete, relevant evidence.** Image results show common and
  scientific names plus the active model, provider, backend, and input source; history thumbnails
  are served from the retained local preview instead of being requested from Frigate. Upload badges
  are icon-only, and manual detections no longer fetch or display unrelated BirdNET-Go context.
- **Photo locations can be recovered and corrected before saving.** Valid EXIF GPS coordinates are
  extracted defensively, shown on an editable map, and retained with the observation. When an image
  has no coordinates, the owner can place a pin or enter latitude and longitude; location remains
  optional and can be cleared.
- **Automatic bird-model regions now understand the country values the setup UI actually stores.**
  ISO-2, ISO-3, and supported human-readable names such as `United Kingdom` and `United States`
  resolve consistently. UK installations no longer silently fall back to North American
  Small/Medium artifacts, and hardware evidence remains bound to the regional artifact it tested.
- **Manual video reclassification is queue-owned, bounded, and cancellable.** The request now
  returns immediately, deduplicates against live/maintenance work, reports real Jobs progress, and
  always runs video inference in a killable subprocess so a timeout or disconnected client cannot
  leave native inference consuming the accelerator.
- **Playable cached media is no longer discarded because Frigate forgot the event.** Manual
  analysis prefers complete or partial cached recordings and cached event clips before a Frigate
  fetch. If event lookup, retention, fetch, validation, decoding, or video inference cannot provide
  usable video, the same job visibly downgrades to the best available snapshot instead of failing
  without attempting the remaining evidence.

## [2.16.0] - 2026-07-25

### Added

- **System status now carries a subtle live host-activity trace.** A lightweight one-minute SVG
  history shows real CPU load and, when the host exposes a supported counter, active accelerator
  utilization. Unsupported or unavailable accelerator data is omitted rather than estimated.
- **Anonymous fleet telemetry now has bounded daily rollups.** Opted-in installations contribute
  one privacy-preserving daily heartbeat snapshot, while accepted health reports retain opaque
  event identities so retries and restart-overlap cannot silently double-count the same evidence.

### Changed

- **The desktop sidebar now matches the rest of the application more closely.** The large centred
  bird mark remains, while navigation is grouped into observation and management areas, the active
  route has a clearer Blue Tit treatment, live system state is shown as compact honest rows, and
  authenticated or public access is presented in a quieter account card.
- **The aggregate telemetry dashboard now separates user metrics from health data.** Each mode has
  its own task-focused hierarchy, 7/30/90-day accessible trend views, bounded runtime categories,
  responsive layouts, and honest empty states instead of presenting both datasets through one
  generic dashboard composition.

### Fixed

- **Sidebar utilities remain reachable on short desktop viewports.** Navigation scrolls within its
  own region while account, theme, language, notification, and collapse controls stay available.
- **Telemetry ingestion is safer under retries, malformed traffic, and free-tier limits.** Request
  sizes and runtime categories are bounded, missing rate-limit bindings fail closed, an atomic
  daily write budget protects both ingestion routes, and 400-day retention cleanup is incremental
  rather than an unbounded maintenance operation.
- **Monolith UI builds no longer trust a partial optional-dependency install.** The image build uses
  the committed lockfile, explicitly includes native build dependencies, verifies Lightning CSS
  before compiling the UI, and retries the clean install once if npm silently skips its platform
  binary.

## [2.15.0] - 2026-07-23

### Added
- **Background work now has one owner-facing status contract.** `GET /api/jobs` reports queued and
  running video analysis, best-quality snapshot, full-visit clip, and backfill work as distinct
  lanes with truthful queue depth, worker concurrency, phase, blocker, and event routes. The Jobs
  workspace and global progress bar consume that server state, keep queued work separate from
  running work, use accessible progress semantics, and retain local live updates only as a
  fail-soft supplement.
- **Crop quality now has a direct Frigate challenger benchmark.** Private field manifests preserve
  same-frame Frigate coordinates, structured classifier baselines, and owner-label provenance. A
  new end-to-end harness classifies the unchanged full frame, Frigate crop, and optimized model
  crop through the active model, reports owner-labelled win/tie/loss outcomes separately from
  automatic context, records crop strategy and latency, and counts hard-negative model crops. It
  also mirrors the production same-identity/two-point guard so raw detector regressions cannot be
  confused with the image the application would actually select. Quark's 30-positive/10-negative
  run found 7 guarded model promotions and 23 Frigate retentions. Its three owner-labelled cases
  produced one improvement, two safe ties, and no guarded loss, while no hard-negative crop reached
  the active `0.40` classifier floor. The harness now applies the same extra context as the HQ path,
  and its direct entry point resolves the backend package in production images.
- **External crop candidates now have a strict, non-promoting benchmark path.** The maintainer probe
  reproduces the official D-FINE/DEIMv2 batch-one ONNX contract, validates shapes and finite output,
  separates positive localisation recall from negative-scene false positives, records compile and
  median/p95 inference cost, and isolates CPU, Intel CPU/GPU/NPU, and CUDA provider trials. Candidate
  artifacts and private camera panels remain outside the runtime registry and release assets.
- **Hardware validation now exercises crop detectors as first-class inference models.** Full sweeps
  download both crop tiers, run each exact artifact in an isolated CPU/CUDA/OpenVINO process, and
  compare finite output plus detection presence, box geometry, and confidence against CPU across a
  round-robin 24-image species panel and three deterministic hard negatives. Diagnostics keeps
  detector rows separate from classifier scoring while showing both in the compatibility UI.
- **Validated crop detectors can use the fastest proven provider.** Crop sessions now support CUDA
  and OpenVINO CPU/GPU/NPU, activate only from current image-specific validation evidence, use
  static accelerator batches and Intel GPU f32 precision where required, and demote to CPU after
  either compile-time or inference-time failure without losing the original-image fallback.
- **Crop validation now uses both broad and field-specific image variety.** Provider sweeps select
  up to 24 taxonomy-verified species round-robin, add deterministic hard negatives, and can be
  complemented by a private same-frame panel builder. The Quark field pass covered 30 independent
  events across seven recorded labels plus 10 real feeder/foliage negatives rather than relying on
  the Sparrowhawk regression alone.
  Quark's corrected run matched the accurate YOLOX detector on all 27 clean/synthetic cases and all
  43 private field/synthetic cases across Intel CPU, GPU, and NPU. The safe field policy admitted
  6/30 distant/mid-distance event crops and 0/13 negatives, leaving replacement-model recall as
  explicit roadmap work rather than overstating hardware equivalence as detector quality.
- **The first two external crop candidates were screened on varied images and Quark hardware.**
  Pinned official D-FINE-N and DEIMv2-N exports were evaluated on eight labelled clean/feeder
  reference images plus 30 independent field events across seven recorded labels and 10 real
  feeder/foliage negatives. At each candidate's most permissive tested zero-false-positive field
  threshold, D-FINE-N produced one IoU≥0.3 crop and DEIMv2-N produced two, versus four from the
  current YOLOX evidence path. Both matched CPU policy presence across all 40 cases on Intel CPU and
  GPU, but the Intel NPU compiler process exited for both static batch-one graphs. Neither candidate
  is promoted; RTMDet-Tiny, PP-YOLOE+ S, manual owner labelling, and downstream classifier comparison
  remain open.

### Fixed
- **A normal deep-video abstention no longer disables later video analysis.** A valid clip with
  weak, ambiguous, hidden, or representation-conflicting frame evidence remains visible as
  `video_no_results`, but is recorded as an informational abstention rather than an inference
  warning and cannot increment either the live or maintenance circuit breaker. Typed
  worker failures, exceptions, and timeouts still count and retain the existing cooldown.
- **Detection intake and background work now degrade safely under bursts and restarts.** BirdNET-Go
  messages use a source-scoped stable detection identity when one is published, making broker
  redelivery idempotent in both persisted history and the live correlation buffer; distinct audio
  observations are processed in order instead of being coalesced away. Frigate false-positive
  tombstones cannot be overwritten by a later pending update, a final event can recover a missed
  initial detection, and post-commit media, notification, or sublabel failures can no longer make a
  saved detection look lost. Automatic video jobs persist `pending` before entering memory and are
  reclaimed after restart. Full-visit generation now uses two bounded workers, HQ overflow is
  capped at 32 pending plus 128 deferred items, classifier progress retains exact frame offsets
  across subprocesses, and shutdown drains MQTT intake before stopping downstream workers.
- **First-run setup now remains secure, truthful, and recoverable across every step.** Enabling
  authentication returns the initial owner token atomically so setup can continue through the
  newly protected API, while serialized first-run claims and rollback on save failure close the
  auth-disabled takeover and partial-write paths. Crop detectors can no longer appear or activate
  as classifiers. Section readiness now checks the credentials required by enabled integrations
  without claiming live health; re-run sections return to their review map; failed refreshes keep
  the last trustworthy summary; save failures are visible; focus is trapped/restored with scoped
  Escape; and model validation has a bounded 30-minute UI deadline. Frigate, MQTT, BirdNET-Go, and
  BirdWeather diagnostics test current or saved-secret-preserving values without mutating config,
  and BirdNET's final stage waits for a real database insert/delete before turning green, then
  removes its synthetic evidence so it cannot affect history or audio confirmation. New setup and
  recovery copy is present in all nine active locale catalogs.
- **First-run configuration can no longer overwrite saved settings after a failed read.** Every
  settings-backed step now has explicit loading, retry, and ready states and keeps Continue disabled
  until the current configuration is known. The connection step supports authenticated MQTT
  brokers without exposing a saved password, the camera step no longer presents the raw classifier
  confidence threshold as a routine choice, and setup offers an opt-in retained-Frigate history
  import that continues as a visible background job. The review summary uses localized structured
  readiness details instead of displaying backend English prose.
- **Historical backfill is now fail-closed and preserves enriched history.** Frigate HTTP, timeout,
  invalid-payload, stalled-pagination, and page-budget failures can no longer look like a successful
  empty import. A higher image-classification score preserves existing BirdNET audio, weather,
  same-species taxonomy, the strongest Frigate score, and sublabel evidence; stale taxonomy is
  cleared when the stronger result changes species. Completed snapshots are now fetched explicitly as
  full frames and, when aligned Frigate box/region metadata exists, reconstruct Frigate's tracked-object
  crop before classification—even when the selected model's own detector-crop policy is disabled.
  Live and backfilled results use the same confidence, blocked-species, abstention, and Frigate-sublabel
  gates; below-floor history remains skipped rather than gaining a backfill-only exception. Already-
  cropped or temporally unaligned cached images are never cropped with stale final-event coordinates.
  An existing row can still repair a missing cached snapshot and enter the HQ replacement path.
  Custom ranges follow the browser timezone with an inclusive final calendar day, automatic weather
  follow-up waits for the maintenance lane instead
  of being dropped, reset cancels and awaits active work before deleting data, and the watchdog
  reports idle jobs rather than penalizing a long job that is still progressing. The Settings result
  surface now exposes reason counts—including an explicit below-confidence count—while vanished
  backend jobs are marked stale rather than falsely completed.
- **The Model Manager now reports the provider that is actually running.** Hardware-neutral
  model recommendations no longer label high-accuracy models as CPU-only, and the active model
  shows its live provider plus the backend's real automatic fallback order. Intel NPU is included,
  unavailable providers stay hidden, and stale installed metadata cannot conceal the active path.
- **HQ snapshots now improve on Frigate instead of accidentally replacing its best work.** Frigate's
  completed-track clean best frame and its snapshot-specific tracked-box crop are scored as protected baselines; a
  recording-derived frame can replace them only with a compatible species result and at least a
  two-point classifier gain. The `end` event upgrades or requeues an in-flight live pass, clean-copy
  failure falls back without cropping a possibly pre-cropped regular snapshot, and both Frigate
  baselines remain available in snapshot repair. The final still is also usable when both the event
  clip and cached recording clip are absent. Time-aligned crops now interpret Frigate
  `path_data` as box bottom-centres rather than centres, removing a half-box vertical offset, while
  final stills cannot double-count as independent video evidence.
- **Monolithic builds no longer depend on a mutable release sidecar.** The bundled fallback
  classifier's `model_config.json` is now checked in and contract-tested against the canonical
  registry, while the pinned Coral model and labels remain checksum-verified. Regenerating the
  public model sidecars can therefore no longer break an unrelated image build with a stale
  Dockerfile checksum.
- **AI crops can no longer win merely because the detector was confident.** HQ ranking no longer
  adds model-source bonuses or detector confidence to species evidence. When a valid Frigate crop
  exists, a model crop must predict the same species and improve the active classifier score by at
  least two percentage points; otherwise the best Frigate/full-frame baseline remains selected.
  The exact model strategy is retained with saved candidates for diagnosis.
- **Reused download filenames no longer corrupt crop-provider comparisons.** Each validation image
  now has a stable unique identity; missing, unexpected, or duplicate rows fail closed. The gate
  compares detections admitted by the most permissive production policy instead of arbitrary
  sub-threshold YOLO noise, removing both false accelerator disagreements and false hard-negative
  detections. The accurate YOLOX-Tiny contract now includes Intel NPU after CPU-equivalent Quark
  validation; the quantized fast SSD remains CPU-only because its OpenVINO graph does not compile.
- **Small distant birds are no longer discarded solely by the normal crop-replacement floor.** The
  accurate detector may admit a box down to `0.02` only in video/HQ multi-representation evidence
  paths, where the full frame remains available and identity, image-quality, temporal-independence,
  and ambiguity gates still decide the result. Thumbnail and direct single-image replacement keep
  the normal `0.05` floor. A manually identified distant Sparrowhawk replay recovered two correct
  crops, including one that outscored Frigate's saved crop; sliced inference and YOLOX-S remain
  benchmark candidates because neither improved downstream classification in that replay.
- **Installed model sidecars can no longer hide a provider validated by the current application.**
  Provider compatibility is now reconciled to the current registry in both directions: obsolete
  sidecar providers are removed and newly supported providers remain available for the hardware
  sweep. The warning identifies both differences without repeating on every status poll. Every
  GitHub-hosted model, label, and external-weight asset is now checksum-pinned in the registry.
- **Raspberry Pi release smoke tests now run the ARM64 image on GitHub's x86 runner.** The smoke
  harness accepts an explicit image platform and the Raspberry Pi job selects `linux/arm64`, allowing
  the configured QEMU emulator to start the ARM-only canary instead of Docker rejecting it as an
  unavailable `linux/amd64` manifest. Mutable Raspberry Pi tags remain blocked until real inference
  passes inside that canary.

### Changed
- **The Jobs workspace is calmer and more operationally honest.** Repeated cards were replaced by
  one divided activity surface, routine automatic work stays out of the global banner, queued and
  running counts are no longer conflated, unavailable server status retries automatically, and
  circuit-breaker recovery uses plain-language actions and translated feedback across all nine
  locale catalogs.
- **Distant-bird localization now uses Frigate-style focus before bounded slicing.** Multi-image HQ
  and deep-video evidence gives YOLOX a square high-resolution search region around the same-frame
  Frigate track when available. Without a trustworthy hint, native inference runs first and only a
  miss on a sufficiently large frame activates four 20%-overlapping tiles. Tiny boxes retain at
  least 160 source pixels of surrounding context, while the full frame and Frigate crop remain peer
  candidates and the existing identity/temporal gates remain authoritative.
- **Full hardware audits can discover stale provider metadata safely.** An owner-only all-model
  sweep can opt into probing every provider packaged by the running image and exposed by the host,
  even when the registry does not yet claim it. Each attempt remains subprocess-isolated and is
  checked on real bird images for finite output and CPU top-1 agreement. Passing undeclared
  providers are reported separately and cannot become runtime-eligible until the reviewed registry
  is updated. Release sidecars are now generated from that registry, keeping provider,
  preprocessing, checksum, and automatic crop-policy metadata reproducible.
- **Raspberry Pi images now start classification-ready and are release-gated by real ARM inference.**
  Every monolith image includes a revision-pinned, checksum-verified MobileNet V2 model and labels
  as an offline CPU fallback. ARM64 now uses Google's current standalone LiteRT interpreter instead
  of the much larger retired TensorFlow ARM package. The Raspberry Pi CI job publishes only an
  immutable canary first, starts it under QEMU, verifies the classifier and label set, runs an
  uploaded image through inference, and only then promotes `dev`, `main`, version, or `latest` tags.
  Compose now passes the documented classifier concurrency, admission-timeout, and Frigate clip
  controls into the container, including the corrected `CLASSIFIER_IMAGE_MAX_CONCURRENT` spelling.
  Physical Pi thermal, sustained-load, and storage validation remains required before support stops
  being labelled best-effort.
- **First-run model setup can now complete without detouring into Settings.** The wizard selects the
  model the runtime actually loaded (including the bundled MobileNet fallback), downloads a chosen
  model with accessible live progress and bounded error recovery, then exposes hardware validation.
  Startup reports a recoverable `model_unavailable` phase instead of claiming `model_ready` when a
  model load fails, while leaving the backend available so the owner can repair the selection.
- **Container startup now reports real progress instead of looking offline.** The monolithic web
  shell stays available while the backend checks inference hardware, loads and self-tests the
  selected bird model, prepares the database, and starts event/media services. The existing
  service-status screen polls a no-cache, non-sensitive phase file and shows a phase-based progress
  bar; it still presents a distinct actionable error when startup fails or the backend is genuinely
  unavailable. The full hardware-validation sweep remains an explicit operator action, and the
  slower accelerated-versus-CPU startup benchmark remains opt-in.
- **Inference provider choices now reflect the runtime that can actually be used.** Settings and
  first-run setup show only providers included in the running image, detected on the host, and
  supported by the active model, ordered from the active runtime through its real fallback path.
  `Auto` remains the recommended default. A saved provider made unavailable by an image, hardware,
  or model change remains visible as a disabled warning until the owner chooses a valid replacement,
  and irrelevant CUDA or Intel diagnostic pills are hidden in provider-specific images.
- **The guided setup now lives with the settings it changes.** `Setup wizard` opens the existing
  non-destructive section map from the Settings navigation's Operations group instead of occupying
  a primary application-sidebar slot; mobile exposes the same action directly beneath the grouped
  Settings selector. The duplicate card remains removed from Data maintenance. The wizard now
  treats an empty camera list correctly as “watch all cameras,” keeps model setup focused on
  compatible model/provider choices instead of exposing execution-process internals, and stops
  writing the legacy crop toggle now that best-image and crop selection are automatic policies.
- **Hardware validation now understands every runtime image.** The setup wizard, guided model
  install, Detection compatibility check and Model Evaluation diagnostics now share one provider
  sweep: `packaged by image ∩ detected on host ∩ supported by model`. It isolates and tests ONNX
  CPU/CUDA plus OpenVINO CPU/GPU/NPU as applicable, compares up to 24 real bird images against a CPU
  baseline, records median inference latency and the fastest verified provider, applies that
  recommendation only after model activation succeeds, and never lets
  OpenVINO CPU hide CUDA in the full image. The setup wizard validates only its selected model;
  Diagnostics can still opt into downloading and testing all models. Compatibility matrices are
  now downloadable through their API route and compatibility-only summaries are populated, fixing
  empty wizard results and stuck fast-completion/error polling. Each model failure is contained so
  the rest of a sweep completes, subprocess timeouts/crashes produce actionable results, failed
  reruns invalidate stale passes, and validation evidence is scoped to the exact image flavor. The
  wizard defaults to the fastest result and offers only providers that passed for its selected model.

## [2.14.0] - 2026-07-20

### Added
- **BirdNET history now connects matching sound and video evidence.** Completed automatic video
  classifications are matched by scientific name, configured time window, and camera/audio source
  mapping; a compact accessible icon opens the exact visual detection. The leaderboard also links
  directly to the full listening history, and event deep links resolve independently of pagination.
- **Distant birds can now be identified from the best high-quality crop automatically.** YA-WAMF
  classifies Frigate-hint and detector crops from several independent clip frames using the active
  model's declared input contract, then promotes only a clear multi-frame consensus. This can
  upgrade an Unknown Bird or strengthen the same existing species, while manual tags, conflicting
  known identifications, low-confidence crops, single-frame duplicates, and ambiguous competing
  results remain untouched. The supporting evidence remains in the saved snapshot candidates,
  deep-video job state stays independent, and `/health` reports refinement outcomes.
- **HQ snapshot recovery now has persistent bounded retry state.** Missing or unusable upstream
  media backs off for five, fifteen, and forty-five minutes and becomes terminal on the fourth
  failed attempt instead of returning to an endless five-minute loop after every restart. The
  state is separate from classification identity, is deleted with its detection, and is cleared by
  a successful automatic or explicit regeneration.

### Fixed
- **Manual video reclassification now uses the video the owner can already play.** An explicit
  video request no longer stops after a confident snapshot preflight: it prefers the cached
  full-visit recording, accepts a decodable partial recording when the ideal window is shorter
  than requested, then tries the cached event clip before Frigate. A fetched full-visit clip also
  selects video reclassification even when stale event metadata still says `has_clip: false`.
  Snapshot analysis remains the defensive fallback only when every video source is absent or
  unusable; an invalid cached candidate is removed and the next video source is tried first. A
  successful cached-video run also clears stale `event_not_found` status.
- **Manual reclassification now treats model abstention as a safe outcome.** When video analysis and
  its snapshot fallback cannot produce a confident species, the API returns `no_result` without
  changing the existing identification instead of returning HTTP 500. Reclassification now emits
  exactly one terminal live event, reports genuine media/runtime failures separately, and keeps a
  video-to-snapshot fallback active rather than briefly presenting it as a failed job. All owner UI
  surfaces show the translated unchanged-result message.
- **Nearby BirdNET history now survives mixed source timezones.** BirdNET timestamps are normalized
  to UTC before indexed storage and an upgrade migration canonicalizes existing rows, fixing valid
  nearby detections being omitted when visual events used UTC while BirdNET-Go published a local
  offset such as British Summer Time. Detection details continue to query the configured persisted
  history and camera/source mapping rather than relying on the short-lived dashboard buffer.
- **Full-visit availability now means complete continuous coverage.** The Frigate capability check
  no longer mistakes long alert/detection retention for a contiguous recording timeline, requires
  an active camera with a real `record` stream role, and requires every selected camera to qualify.
  Per-camera retention correctly overrides the global value, and the UI reports the guaranteed
  minimum rather than the most optimistic retention. A quiet inline Settings status now names each
  affected camera and explains the exact corrective action, while an already-enabled setting can
  still be switched off safely.
- **Late BirdNET detections now appear in visual detection details.** Opening a detection checks
  persisted audio history with the configured time window and camera/source mapping, even when no
  audio hint was stored during visual ingest. Nearby sounds remain clearly separate from a confirmed
  visual/audio species match, and rapid previous/next navigation cannot show stale audio context.
- **Guest detection details no longer expose an unusable reclassify action.** The low-confidence
  video-result notice now applies the same owner-access guard as every other mutation control.
- **Image classification evidence is now kept in its correct domain.** Manual species corrections
  are protected by the same SQL statement that performs any automatic write; Frigate object score
  is no longer treated as sublabel confidence; local inference runs before a trusted Frigate
  fallback; BirdNET-Go confirmation no longer replaces visual confidence; and MQTT `update` can
  recover a missed `new` event without repeatedly classifying detections that already exist.
- **Deep-video classification now abstains on temporal ambiguity.** At least three frames must be
  evaluated, low-confidence and non-species frames count as abstentions, and a species needs at
  least two supporting frames plus 60% of evaluated frames. Confidence is the supporting-frame
  median, preventing one extreme frame from determining the visit. Full frames, valid Frigate-box
  crops, and detector crops now build independent temporal consensuses rather than becoming extra
  votes; conflicting representations cause an abstention, while agreeing representations select
  the strongest evidence. The exact winning input is persisted and shown in detection details, and
  snapshot fallbacks are labelled as snapshots rather than presented as video evidence. Snapshot
  provenance follows any model-driven crop that actually reached preprocessing, while cache
  metadata continues to describe the retained media; historical backfill no longer assumes an
  ended Frigate event honoured the live-only `crop` query.
- **Best-available snapshot selection now rejects misleading crops without sacrificing the HQ
  frame.** Crops must retain usable detail and agree with the known detection identity (or repeat
  across independent frames before identity exists); sharpness, exposure, resolution, classifier
  evidence, and crop confidence share one ranking. The canonical and best full-frame candidates are
  retained even when the bounded candidate list is crowded.
- **HQ crop consensus now uses genuinely independent moments.** The snapshot worker no longer
  treats `target - 1`, `target`, and `target + 1` as three observations. It keeps a centre/track-
  weighted target, distributes the remaining slots across the tracked interval or central clip
  region, requires at least 250 ms between votes, and uses neighbouring frames only to recover a
  failed decode within the same slot. Frigate hint boxes follow the nearest timestamped path point
  on event clips; unaligned recording timelines fail safely to the model detector or full frame.
- **Inference failures can now activate provider recovery.** ONNX execution/output failures are
  typed instead of collapsing into an empty result, HQ candidate scoring uses supervised background
  admission in both in-process and subprocess modes, and TFLite signed-int8 tensors honour scale
  and zero point rather than being fed float bytes or misread as raw logits.
- **Playable short recordings are no longer deleted and downloaded again forever.** Measurable
  partial clips are retained and reused for HQ/video work, while stubs and unmeasurable corrupt
  media remain ineligible.
- **Deployment refresh recovery now shows a real, localized message instead of
  `error.deploy_refresh_required`.** The browser performs at most one automatic reload for each
  backend build it encounters, reports the frontend/backend identities and recovery action through
  client diagnostics, and emits only one warning for a mismatch that remains unresolved. A later
  deployment can still trigger its own bounded recovery attempt, without trapping a tab in a reload
  loop. This resolves #100 and explains why affected installations had no corresponding backend log.

### Changed
- **The Unraid template now makes the runtime/provider contract explicit.** It keeps the safe full
  image and in-app `Auto` selection as defaults, documents CPU/Intel/CUDA tags and Intel/NVIDIA host
  setup, and warns against environment overrides that would make the provider selector revert after
  restart. Image packaging, hardware exposure, selected provider, and active provider are presented
  as separate states.
- **Inference runtimes are now available as smaller provider-family images without changing the
  compatibility path.** Unsuffixed monolith tags remain the full CPU/CUDA/OpenVINO image, while
  additive `-cpu`, `-intel`, and `-cuda` tags package only the selected runtime family and retain
  CPU fallback. Every image reports its flavor separately from hardware availability, and an
  explicit provider/image mismatch is visible in classifier diagnostics. Runtime images no longer
  retain their build wheelhouse or install pytest, Coverage, and Ruff, reducing distribution size
  without changing `/config`, `/data`, models, migrations, or application behaviour. The dedicated
  Raspberry Pi image now explicitly uses the CPU dependency set and standalone LiteRT interpreter,
  while non-Linux ARM development environments retain their native TensorFlow package. Pinned Intel NPU driver assets
  are checksum-verified and required, preventing a full or Intel image from publishing with a
  silently incomplete runtime. Mutable flavor tags are now promoted only after every immutable
  image starts successfully and a full → CPU → full round trip preserves byte-identical application
  config, model artifact and model sidecar, SQLite integrity, Git identity, and an intentionally
  incompatible provider setting. Setup, troubleshooting, API, model-testing, development, and
  release documentation use the same packaging/availability/active-state vocabulary and preserve
  the established `YAWAMF_MONALITHIC_*` Compose variable spelling.
- **Routine dependency updates now keep runtime compatibility explicit.** Frontend charts use the
  ApexCharts 6 slim core rather than shipping its opt-in authoring feature set, telemetry changes
  are compiled in CI instead of merely installed, and GitHub workflows use setup-node 7. The
  x86-64 ONNX Runtime GPU dependency is capped to the validated CUDA 12 line until CUDA 13 packages
  are available from the normal package index; CI now declares coverage.py directly instead of
  carrying the unused pytest-cov plugin.
- **The full translation editorial sweep is complete across all nine catalogs.** Every locale has
  the same 1,981 leaf keys and matching interpolation tokens. Copied English enrichment guidance,
  accent-stripped settings and video-player strings, Russian open-source terminology, Japanese
  spacing, French punctuation spacing, stray catalog whitespace, and application-wide ellipsis
  typography have been corrected. A new CI gate catches encoding damage, whitespace, ASCII prose
  ellipses, known accent-loss regressions, French double-punctuation spacing, and sentence-length
  Latin-only copy in Japanese, Russian, or Chinese. This is an application/editorial review, not
  independent native-speaker certification; that limitation remains explicit for the 3.0 release.

## [2.13.0] - 2026-07-19

### Fixed
- **Owner diagnostics no longer expose internals or accept unsafe resource targets.** BirdNET-Go
  reachability validates an HTTP(S) base URL, rejects embedded credentials and redirect traversal,
  model-evaluation artifacts resolve only through existing canonical run directories, and classifier
  diagnostics keep exception details in server logs instead of returning tracebacks to the browser.
- **Logged-in sessions no longer grow progressively slower in long-lived tabs.** Authentication
  changes now replace the live Server-Sent Events connection and discard owner-only settings when
  a session becomes a guest session. Analysis queue status has one single-flight, adaptive poller
  instead of competing five-second loops, hidden tabs pause routine network work, and health,
  diagnostics, cache, analysis, and camera-preview requests have bounded timeouts. Camera preview
  images are fetched only while their popover is open rather than continuously in the background.
  Full-visit availability now performs one bounded follow-up check instead of re-probing every
  visible historical event indefinitely, keeps a finite event-state cache, and contains automatic
  fetch failures. Explorer requests cancel superseded pages without letting stale results overwrite
  current filters, shared detection loading is single-flight, and Leaderboard enrichment is
  concurrency-limited with stale loads aborted and its portrait cache bounded. Auth recovery and
  status endpoints now time out defensively; dashboard audio refreshes wait for the previous request,
  stop while hidden, and abort on navigation; slow Settings and model-download status checks cannot
  overlap and accumulate work.
- **Live camera previews remain owner-only when Guest Mode is enabled.** The latest-frame endpoint
  now enforces the same owner dependency as other administrative Frigate routes and returns
  explicit no-store headers, so an unauthenticated visitor cannot retrieve a current camera frame
  merely because read-only public browsing is enabled.
- **Authenticated tabs now converge safely after every dev deployment.** YA-WAMF compares the
  concrete frontend and backend Git identities instead of ignoring build metadata, registers the
  service worker against the exact build with uncached update checks, and rate-limits operational
  polls even if their lifecycle is retriggered. Existing `2.12.0` tabs are forced onto `2.12.1`,
  preventing stale owner sessions from flooding health and diagnostics endpoints and progressively
  slowing the interface.
- **The About page now matches the rest of the refreshed interface.** Its section, feature, step and
  resource icons use the same bordered, tinted chip as the Leaderboard and Species pages instead of
  a flat wash that nearly disappeared against the dark background, and its links and buttons now come
  from the shared button kit rather than hand-rolled styling, so their corner radius, surface and
  hover colour match every other page and follow the active colour theme.

### Added
- **Guided model install with on-hardware validation and device auto-tuning.** Setting up a
  classifier is now one guided wizard: **download** (with live progress in the dialog) → **run on
  your hardware** (pushes frames through the model, confirms valid output, and reports per-frame
  latency) → **find fastest device** (sweeps CPU / Intel GPU / NPU and sets your inference provider
  to the fastest one that passed) → **enable**. A model that has never been validated on this host
  can no longer be made active (the model already running and the bundled default are unaffected),
  so you find out a model does not run on your hardware at install time instead of when the next
  bird shows up. Validation works on every host — CPU-only, NVIDIA CUDA, and Intel/OpenVINO alike.

### Changed
- **Python lint and formatting now cover every tracked Python path, enforced in CI.** `ruff check`
  and `ruff format --check` previously ran only against `backend/` and `custom_components/yawamf/`,
  leaving `scripts/` and `tests/` unchecked; both now run repo-wide from the repository root, so a
  new top-level Python directory is covered automatically rather than silently skipped. The nine
  bare `except:` clauses this exposed in the Playwright end-to-end suite now catch the specific
  Playwright errors they were meant to tolerate, so a real failure surfaces instead of being
  swallowed by a fallback path. Remaining unused imports, empty f-strings, unused locals, a lambda
  assignment, and one-line conditionals in `scripts/` and `tests/` are cleared, and those files are
  formatted to the repo style.
- **A fresh install now opens in dark mode** instead of following the operating system setting, so
  the interface matches the shipped bluetit and classic-typography defaults out of the box. Anyone
  who has already chosen a theme keeps their choice, and Light / Dark / System remain available under
  Settings → Appearance.
- **Live camera status is now honest, lightweight, and useful before the viewer opens.** The header
  polls Frigate's stats feed through a normalized owner-only YA-WAMF endpoint instead of treating
  unfetched preview images as failed cameras: green means every camera is live, amber means a mixed
  result, red means every known camera is offline, and a neutral state covers checking or unavailable
  status. The preview is now one edge-to-edge camera surface with an overlaid name/status pill,
  touch-sized previous/next controls, keyboard navigation, click-outside/Escape dismissal, and
  infinite wrapping. Only the selected camera frame is fetched while the viewer is open, and hidden
  tabs suspend both health and frame work.
- **The Dashboard and About pages read more consistently.** The Dashboard overview no longer
  repeats the page title and subtitle inside its own card — it now leads with a "Last 24 hours"
  section header and a live indicator. The About page adopts the same calm section-header language
  used across the refreshed pages (a tinted accent icon beside each heading), quiets its feature
  badges and jump-links, and lists OpenVINO in the machine-learning stack alongside ONNX Runtime.
- **The interface leans harder on one calm teal identity.** Decorative accent colours that had
  drifted into the leaderboard (a violet, cyan, and sky section flourish) are folded back into the
  teal palette, while colours that actually carry meaning — chart-series keys, the temperature /
  wind / precipitation overlay legend, up/down trend deltas, and status — are kept exactly as they
  were. Section-icon shapes are unified, and a set of unused decorative style utilities (a hover
  card-lift, gradient stat text, an animated header line) is removed so nothing reintroduces the
  louder look.
- **The refreshed surfaces now share one typographic and control language.** Headings and labels
  across the Dashboard, Explorer, Species, BirdNET-Go History, and the detection detail dialog now
  use a single weight the interface font actually ships, so text no longer renders as a synthetic
  heavier weight on some screens than others. Section eyebrow labels are calm sentence case instead
  of loud all-caps, and the Explorer multi-select toolbar uses the shared button kit in the app's
  teal/emerald palette (with the destructive action still clearly styled as destructive) rather than
  one-off indigo and cyan controls.
- **The bcrypt 5 upgrade preserves access for existing installations.** Newly configured owner
  passwords are validated against bcrypt's 72-byte UTF-8 limit before they can be saved, while
  sign-in retains bcrypt 4's legacy truncation behaviour for existing longer passwords. Clear
  first-run and Security guidance prevents an accepted password from failing later at hash time.
- **The interface now arrives quickly instead of loading the whole application up front.** The
  entry bundle is reduced from roughly 2.4 MB to 157 KB by loading operational pages and
  translation catalogs only when they are needed. Fingerprinted assets are compressed and cached
  immutably, while the application document is always revalidated after a deploy. Fast route
  changes no longer flash a wall of skeletons; slower connections get one quiet status line, and a
  failed page or language download can be retried in place with an English startup fallback.
- **Explorer and detection details now put the visit before the interface.** Event filters and the
  timeline use quiet divided toolbars instead of stacked cards, pagination no longer adds another
  floating panel, and detection tiles keep their media-led hierarchy without lift, rotation, or
  pulsing confidence decoration. Detection details preserve the complete snapshot instead of
  cropping it again inside the dialog, collapse the Frigate event ID as technical context, and use
  restrained section dividers for audio, weather, and supporting evidence. The responsive dialog
  now fills small screens safely while retaining every video, HQ snapshot, species, and owner action.
- **The Dashboard is now a calm live observation desk.** A single first-run-inspired overview
  replaces the row of repeated metric cards, the newest camera visitor stays the visual anchor, and
  activity plus BirdNET-Go detections form a compact supporting rail instead of competing panels.
  Top visitors are a ranked, touch-friendly field list with circular species recognition portraits
  and no redundant heading glyph, while the Species metric uses a crisp field-guide feather instead
  of the ambiguous miniature bird mark. The separate discovery cards remain only where each
  detection is genuinely interactive.
  The Leaderboard now uses the same circular portraits in its featured record and both ranking
  layouts, keeping species recognition consistent across the application.
- **The service-unavailable screen now belongs to the current application.** The legacy warning card
  is replaced by the same restrained teal, typography, spacing, and application identity used by
  first-run setup. It explains that feeder data remains safe, checks recovery automatically every
  five seconds, shows progress on manual checks, and gives the operator a useful container-health
  next step. Operational polling now waits for a healthy backend instead of multiplying a startup
  outage into repeated failing requests.
- **High-quality snapshots now mean the best crop the system can produce.** Settings exposes one
  outcome-oriented control instead of separate HQ-frame and crop switches, with a compact detector
  readiness note. For each candidate frame, YA-WAMF evaluates Frigate's tracked-object crop and the
  installed crop detector, ranks every valid crop, and uses the strongest one; the full frame is
  kept only when no reliable crop exists. Legacy crop-source preferences remain API-compatible but
  can no longer silently force a worse image.
- **The Leaderboard now prioritises rankings over decoration.** A calmer field-journal layout
  replaces the repeated featured, highlight, performer, chart, and table cards with one featured
  record, a divided highlights strip, the complete rankings, and secondary analytics. Desktop keeps
  a semantic comparison table while phones get a native vertical ranking list instead of a
  900-pixel horizontal scroller. Numeric rank markers replace emoji medals, labels and controls are
  readable and touch-sized, source switching now genuinely reorders by Seen, Heard, or Both after
  deduplicating merged BirdNET species, and pressed-state / table-heading semantics make those
  controls clearer to assistive technology.
- **BirdNET-Go History now works as a listening log, not a card dashboard.** The summary is one
  quiet divided strip, filters sit directly above the primary detection record, and each page is a
  manageable 25 detections. Desktop keeps a semantic comparison table while the same rows reflow
  into a compact, spectrogram-led phone log without horizontal scrolling. Activity charts, top
  species, and source totals remain available as secondary evidence below the log; top-species rows
  open the same species-detail record as the Leaderboard. Restrained dividers, readable chart
  labels, honest loading/empty/error states, and in-place retry complete the view.
- **Species details now read as a field record, not a card dashboard.** The refreshed full-height
  mobile / wide desktop dialog leads with the feeder's own detection totals and recent sightings,
  then moves into the species photograph, reference material, wild-observation context, activity,
  and camera breakdown. Repeated coloured cards and duplicate headings are replaced by restrained
  dividers and one clear content hierarchy, while video affordances, focus states, reduced motion,
  body-scroll locking, readable labels, and in-place error recovery make the view work better by
  touch, keyboard, and assistive technology.
- **RoPE ViT-B14 can use validated Intel GPUs.** The registry now includes `intel_gpu` after the
  full Quark Arrow Lake-S sweep on OpenVINO 2026.2.1 compiled RoPE on CPU, GPU, and NPU, produced
  finite output on 12 real comparison images per device, and matched CPU top-1 on every GPU/NPU
  image. The older OpenVINO 2025.4 NaN evidence remains documented, so the per-host validation gate
  still decides whether a specific Intel GPU is safe before selection.
- **Host-validated model devices no longer raise contradictory config warnings.** The shared model
  registry remains conservative for hardware that has not been tested, but a provider proven by
  this host's isolated device sweep is now merged before classifier status is assembled. YA-WAMF
  therefore no longer reports an installed-provider warning while successfully running that same
  provider; unrelated model-sidecar warnings remain visible.
- **Validated ONNX models now advertise Intel NPU support.** The same Quark sweep adds `intel_npu`
  to the nine standalone ONNX classifiers that compiled, returned finite output, and matched CPU
  top-1 on all 12 real NPU comparison images. TFLite MobileNet stays CPU-only, and regional
  Small/Medium families remain unflagged until EU and NA artifacts are recorded independently.
- **Classifier cropping and cropped thumbnails are now clearly separate.** Classifier crop-on/off
  policy remains automatic and evidence-based per model. The subtle **Cropped thumbnails**
  disclosure reports the automatic Accurate → Fast fallback and detector readiness instead of
  asking users to choose an implementation tier. The crop-policy harness rejects runs where crop-on
  silently fell back to full frames.
- **Every connection test now looks and behaves the same.** The AI model test, the Frigate & MQTT
  connection test, the BirdNET-Go test, the BirdWeather test, and the Discord / Telegram / Pushover /
  Email notification tests all use one shared guided dialog with a stepped checklist that advances
  as each check passes. Settings → Integrations also gets calmer
  card headers with a subtle icon per service, and the settings navigation drops its blue accent
  stripe for the same teal/emerald used across the rest of settings.
- **Settings panels read more consistently.** Each panel card now leads with a matching icon and,
  where it helps, a one-line summary of what it does. Settings → Detection opens with a short
  description and keeps its confidence slider up front, with model management, fine-tuning, and
  runtime diagnostics tucked into their existing advanced sections.
- **Fewer rarely-touched options up front.** Settings → Connection now tucks the full-visit
  recording-clip feature behind an advanced disclosure (basic "fetch clips" stays visible), matching
  how Authentication already hides session expiry, trusted proxies, guest day-windows, rate limits,
  and the external URL. Anything hidden this way still has an environment-variable override.

- **Telemetry opt-in moved into first-run setup.** The standalone telemetry banner is gone; new
  installs are asked once, as a clear opt-in step in the guided wizard (off by default, no personal
  data). Existing installs enable it any time from Settings.

### Documentation
- **Every environment variable is now documented.** A new
  [Environment variables](docs/setup/environment-variables.md) reference lists every override the
  config loader reads — names, defaults, and the handful of settings that are UI/file-only —
  linked from the configuration guide and docs index.

### Fixed
- **Owner sessions no longer slow down under an active background job.** Operational polling is
  isolated from the reactive job state it updates, preventing a feedback loop that could flood the
  browser and backend with health, cache, analysis, and diagnostics requests. Startup, timer, and
  tab-focus triggers now share each in-flight request instead of starting overlapping work.
- **Optional runtime benchmarking can no longer strand application readiness by default.** The
  synthetic accelerated-versus-CPU comparison is now opt-in through
  `CLASSIFIER_RUNTIME_BENCHMARK_ENABLED`; model activation validation, accelerator self-tests, and
  runtime health fallback remain active. This prevents a slow OpenVINO CPU baseline probe from
  holding Uvicorn before it can serve `/health` or the API.
- **High-quality crop generation recovers from real detector misses and restarts.** The accurate
  detector now retries with the fast tier after no-candidate, low-confidence, too-small, invalid-box,
  or inference-failure outcomes—not only when its model file is unavailable. A bounded background
  reconciliation pass also reschedules recent detections that lost their in-memory HQ job during an
  application restart, while leaving completed and manually reverted candidate sets alone. Health
  diagnostics now report the automatic policy, selected source counts, and recovered-job count.
- **The BirdNET-Go test now actually checks BirdNET-Go.** It previously only published to MQTT and
  injected a mock detection into YA-WAMF's own pipeline — never touching BirdNET-Go. When a
  BirdNET-Go URL is configured, the test now first confirms the BirdNET-Go server answers over HTTP,
  then checks the MQTT broker, then the detection pipeline — three honest, separate steps.
- **The AI model diagnostic now dims the whole screen and steps through its checks.** When you
  tested a model, the frosted backdrop stopped short of the top of the page — the running-jobs banner
  showed straight through it. The dialog is now rendered above all page chrome, so the blur covers
  the entire window like the first-run setup. It reads calmer too: the five checks are one connected
  list that reveals a step at a time as each one resolves (a step only turns green when its check
  actually passed), instead of five separate cards appearing at once.
- **Settings → AI leads with what you came for.** The panel now opens on Model Configuration
  (enable, provider, API key, model, and test) with a matching icon, and the 30-day usage figures
  move to a collapsed section underneath. The "get an API key" provider links only appear until a
  key is saved, so a configured install stays uncluttered.
- **Stable installs now pull the stable image.** The recommended monolithic Compose file and
  `.env.example` now default to `:latest`; following the README or Getting Started guide no longer
  starts the potentially unstable `:dev` channel unless you explicitly select it. The first-run and
  password-reset documentation now also matches the guided setup state machine, including the two
  fields required to reopen setup safely after a lost password.
- **AI provider failures are no longer saved as naturalist notes.** Retryable OpenRouter failures
  now keep their HTTP status and optional `Retry-After` header through the event, leaderboard, and
  conversation routes, while failed event analysis leaves the cached analysis empty. Gemini
  exception messages also redact API keys embedded in request URLs.
- **Bird crops now actually appear as the event image.** The displayed snapshot now evaluates every
  available crop source (Frigate box and detector model), chooses the strongest valid crop, and uses
  the full frame only when no crop could be produced. Previously
  `frigate_hints_first` silently fell straight to the full frame whenever the Frigate event was
  unavailable (common on feeder cams, and with short event retention), so the model crop was
  generated but never shown. Small crops are no longer suppressed in favour of the full frame.

### Added
- **Guided AI model diagnostic:** Settings → AI now opens a wizard-style diagnostic when testing a
  model. It reports configuration, provider availability, vision input, five-frame request
  admission, and response generation as separate stages; preserves retryable 429/503 details and
  `Retry-After` guidance; and sends five representative 1280×720 JPEG frames so the check matches
  the production frame count, dimensions, and approximate payload size.
- **Current LLM model selection:** Settings now offers the current provider families: Gemini 3.1
  (`gemini-3.1-flash-lite` and the Pro preview), OpenAI GPT-5.6 (Sol alias, Terra, and Luna), and
  Claude Opus 4.8 alongside the current Sonnet/Haiku tiers. OpenRouter presets use its verified
  provider-specific slugs. Stored legacy presets migrate to current equivalents, the backend
  default is Gemini 3.1 Flash-Lite, and pricing/help documentation is synchronized.
- **Translation contract gate:** The 3.0 translation review has started with a full structural
  comparison of every locale against `en.json`. The frontend test suite now rejects obsolete
  extra keys and any new missing keys beyond the explicit baseline, preventing translation
  drift from silently growing while the remaining Audio History, update, telemetry, and advisory
  strings are translated in reviewable batches. The first batch adds shared Audio History
  navigation, apply/pagination controls, and Intel NPU/public-dashboard telemetry copy in all eight
  non-English locales. Update messaging, the Frigate media-health advisory, and the Audio History
  subtitle are also translated. Dashboard audio copy, Leaderboard source controls, and the full
  Audio History surface complete the remaining work: all eight non-English locales now exactly
  match `en.json`, with no missing or extra keys. The contract also verifies interpolation
  placeholders across every translated string. The language-quality pass has also localized the
  Gemini, OpenAI, and Claude key-acquisition actions in every locale, plus the Japanese orientation
  labels, with semantic regression coverage for the provider actions. A measured sweep confirmed no
  full English sentences survive untranslated in any locale (the byte-identical strings that remain
  are brand/protocol names, URL/host placeholders, and legitimate cross-language cognates), so the
  residual review is a per-language native editorial polish rather than missing translations. To keep
  it from regressing, a baseline ratchet (`locales.identical-baseline.json` +
  `locales.untranslated-regression.test.ts`) now fails CI if any *new* user-facing string lands
  byte-identical to English, guiding the change to either translate it or record a genuine
  brand/cognate in the baseline.
- **Multi-part first-run setup wizard (re-runnable):** The one-screen first-run prompt is now a guided, multi-step wizard that walks a new install through language, admin account, Frigate & MQTT connection (with a live test), cameras & detection threshold, classifier model with on-hardware validation (detected accelerators + a device-sweep compile/latency check), automatic best-available snapshots, and optional integrations, ending on a review screen. Every step is skippable, shows determinate progress, and validates in place. Crucially it is **re-runnable at any time** from Settings → Data → Setup wizard: it opens on a section map (Ready / Needs attention / Optional, from the new `GET /api/setup/state`) so you can jump straight to one section and reconfigure it — each step writes only its own slice through the secret-preserving settings write, so re-running one section never touches the others. Built to the codified UI/UX standard (Nielsen wizard/onboarding guidance, WCAG 2.2 AA).
- **Researched engineering standards codified:** Two authoritative-sourced standards now govern how the project is built, ahead of the 3.0 code-quality review and UI refresh. [`docs/standards/code-quality.md`](docs/standards/code-quality.md) sets the code-craft bar for the stack (PEP 8/typing + async + layering for Python/FastAPI, strict TypeScript with no `any`, and disciplined Svelte 5 reactivity — `$derived` before `$effect`), and [`docs/standards/ui-ux.md`](docs/standards/ui-ux.md) sets the interface bar (Nielsen's 10 usability heuristics, WCAG 2.2 Level AA accessibility, and Refactoring UI visual craft). The enforceable rules are pulled into `CLAUDE.md` §4 and §5; both standards cite their sources.
- **In-app update prompt:** YA-WAMF now detects when a newer build is available and surfaces it — a calm banner (with a link to the release notes) plus a small icon-only indicator in the sidebar status area (an upgrade icon with a pulsing accent and an on-hover version tooltip) — so installs on old builds know to update. It's a *notification only*: YA-WAMF never updates itself; pulling the new image stays with your container orchestrator. It's **channel-aware** — branch images compare against the matching D1-published branch row (`dev` or `main`), while release images compare against the D1-published `stable` row, so a dev box is never nagged about releases. The telemetry worker's `/version` endpoint reads those CI-published rows from D1 as the source of truth. It's a single anonymous request with no telemetry payload — works even with telemetry disabled — and degrades silently if the check fails. Disable via `SYSTEM__UPDATE_CHECK_ENABLED=false`.
- **Recording-frame classification fallback:** When a detection has no snapshot, thumbnail, or cached image, YA-WAMF now extracts a frame from Frigate's continuous recording at the detection moment and classifies that instead of dropping the detection outright. This targets the fleet's most common real failure (`drop_classify_snapshot_unavailable`, seen on 8 of 13 telemetry installs) — briefly-tracked birds whose event snapshot is never persisted are usually still in the recording. On by default (`frigate.recording_frame_classification_fallback`); requires Frigate recordings, and falls through to the existing drop behaviour when the recording isn't retained. See [the design note](docs/plans/2026-07-10-recording-frame-classification-fallback.md).
- **In-app "Event Not Found" guidance:** The Errors/diagnostics page now shows a calm advisory when a material share of recent detections are being dropped because Frigate had no snapshot/media for them (≥15% over a real sample), explaining the likely cause (briefly-tracked birds that never persist, or short recording retention) and linking to the [Frigate Event-Not-Found guide](docs/troubleshooting/frigate-event-not-found.md). This helps users fix the root cause rather than silently losing history; it stays hidden until the rate is genuinely elevated.
- **Unraid Community Applications repository profile:** Added `ca_profile.xml` at the repository root — the maintainer/overview metadata (non-empty `<Profile>`, icon, project link) that Community Applications requires for a new repository submission. Uses the current `<CommunityApplications>` schema and complements the existing `unraid/yawamf.xml` Docker template.

### Changed
- **Settings navigation now follows the feeder workflow.** The flat eleven-tab strip is grouped into
  Feeder pipeline, Intelligence & sharing, Operations, and Interface sections on desktop, with the
  same structure exposed as native option groups on mobile. Desktop destinations are real links with
  consistent outline icons, 44-pixel targets, visible focus, and a non-colour active cue. The
  Connection camera selector now uses separate native buttons instead of nesting preview and role
  actions inside a simulated button, and preview loading/errors are announced. Detection has been
  reduced from up to five peer-level cards to two: active model, confidence, and species exclusions
  stay visible, while model management, fine tuning/video recovery, and hardware diagnostics sit
  behind focused disclosures. The grouped navigation is now one quiet wizard-style surface instead
  of four competing cards. Model Manager has also been rebuilt around selection, readiness, best fit,
  and one download/activate action, with architecture, providers, runtime health, and automatic image
  preparation in Technical details. Runtime warnings still surface immediately. The same treatment
  now covers every Settings tab: optional AI,
  integration, notification, authentication, and public-access fields render only when enabled;
  telemetry, appearance extras, AI usage, data maintenance, and destructive actions use focused
  disclosures; active maintenance work reopens its controls automatically; and Enrichment status is
  a compact divided list instead of nested cards. Structural card emoji and sub-12-pixel Settings
  text have been removed while preserving the Blue Tit theme and existing configuration contract.
- **Classifier crop policy is now automatic and evidence-based.** Every classifier and EU/NA family
  variant has an explicit policy from a 4,032-classification Quark sweep of the production pipeline.
  Classifier crop mode and crop source are no longer routine Settings controls. Crop-detector tier
  remains a separate cropped-thumbnail quality choice. The app
  registry is authoritative over stale installed sidecars, the upstream release sidecars carry the
  same defaults for new downloads, and legacy override fields remain API-compatible but are ignored
  during normal runtime. The feeder harness can select EU or NA explicitly for repeatable retests.
- **Code-quality review — owner debug API:** Started the roadmap's file-by-file review with the
  contained owner diagnostics surface. Debug endpoints now publish explicit response models,
  database counts live behind a repository instead of router-level SQL, model-directory inspection
  runs outside the async event loop, and configuration redaction is a pure tested transform using
  the standard `***REDACTED***` marker. Owner-only access remains unchanged.
- **Code-quality review — formatting baseline:** Formatted the two remaining backend files that
  fell outside the Ruff baseline, making the repository-wide Python format check clean before the
  deeper service and router review batches.
- **Code-quality review — live updates:** Removed application-level `any` from the root SSE wiring
  and live-update coordinator. Untrusted JSON is now accepted as `unknown`, narrowed into explicit
  event contracts, and normalized before reaching the detection store; health, notification, logger,
  and translation dependencies now carry their real types. Added regression coverage for required
  detection-field normalization.
- **Code-quality review — API and operational stores:** Replaced permissive payload types across
  maintenance/system clients, detection state, health cards, incident reconciliation, diagnostics
  snapshots, and reclassification recovery. External data now enters these modules as `unknown` or
  generated API types and is narrowed through small record helpers before property access.
- **Code-quality review — shared components:** Added explicit contracts for navigation items,
  settings tabs, camera roles, model runtime health, UI events, timers, translation callbacks, and
  notification error payloads. This removes another set of application-level `any` escapes from the
  reusable component layer while preserving existing behavior.
- **Code-quality review — chart and map adapters:** Contained dynamic vendor behavior at the
  ApexCharts and Leaflet adapters with typed constructors, instances, map layers, DOM extensions,
  and guarded option records. Chart and map consumers no longer inherit `any` from those libraries.
- **Code-quality review — Events and Health:** Added explicit date-filter admission, reusable bird
  naming inputs, structured diagnostics-health metrics, and safe unknown-error extraction. The two
  page surfaces no longer rely on `any` for URL state, API failures, or health payload traversal.
- **Code-quality review — Species analytics:** Typed the complete leaderboard chart pipeline,
  including weather lookup keys, comparison series, Apex options/axes/tooltips, stable config
  serialization, chart capture, temperature units, and analysis errors. The page no longer uses
  application-level `any`.
- **Code-quality review — Audio and detail modals:** Typed Audio History chart options and removed
  permissive casts from detection/species enrichment, conversations, iNaturalist actions, manual
  tagging, snapshot repair, and owner actions. Errors are now narrowed consistently from `unknown`.
- **Code-quality review — Settings and frontend type gate:** Replaced Settings casts with explicit
  domain normalizers for themes, inference providers, retention modes, and missing-media policy;
  standardized unknown-error handling and typed shared input attributes. A new source audit test
  rejects explicit `any` anywhere in application TypeScript/Svelte outside generated contracts.
- **Code-quality review — backend endpoint contracts:** Started the backend API pass by giving the
  initial-setup, logout, Settings integration tests, Settings import/update, and video-circuit reset
  actions explicit response contracts and return annotations. Classifier status, upload tests,
  rich classification, runtime probes, and owner diagnostics now publish contracts as well.
  Backfill reset/status, regional model-family resolution, update status, species-cache clearing,
  and AI-usage clearing are also generated into the client contract. The Events list/delete/manual
  tag routes and model-evaluation run actions now complete the pass; the evaluation artifact route
  is explicitly documented as a file response.
- **Code-quality review — persistence boundaries:** Moved cache-cleanup event enumeration and manual
  species corrections behind `DetectionRepository`, and moved logout's OAuth-token purge into a
  dedicated repository so these HTTP routes no longer own SQL statements. The eBird export query
  and date filtering now live in `EbirdRepository` as well. Species taxonomy/cache/search queries
  and the complete video-share lifecycle have also moved into focused repositories, leaving no
  direct database execution in the HTTP router layer.
- **Code-quality review — classifier download I/O:** Moved model-directory operations, archive
  extraction, model/label writes, and synchronous classifier reloads off FastAPI's async event loop.
- **Code-quality review — async blocking I/O:** Offloaded database backup/migrations, image decode
  and synchronous inference entry points, temporary video work, media-cache retention scans,
  model-evaluation artifact/image operations, model discovery/activation, and AI recording reads.
  These paths no longer stall unrelated requests while performing filesystem or CPU-bound work.
- **Code-quality review — backend architecture gates:** Added permanent source audits for endpoint
  response contracts, repository-only database execution, complete repository signatures, async
  blocking I/O, untracked TODO/FIXME notes, and stray `print()` calls. Binary, streaming, redirect,
  and downloadable routes now explicitly declare their response classes.
- **Code-quality review — test isolation:** Kept the video-classification scheduler importable with
  the lightweight classifier doubles used by pressure tests while retaining the production live
  classifier resolver, and regenerated both committed OpenAPI artifacts after response classification.
- **Code-quality roadmap complete:** Finished the file-by-file frontend/backend review and closed
  the roadmap item. Final verification: 1,390 backend tests passed with 79% coverage (65 expected
  platform/model skips), 408 frontend tests passed, Svelte check was clean, the production build
  succeeded, and lint, formatting, migrations, docs, OpenAPI, and generated client checks passed.
- **API contract — typed integration responses:** The email OAuth authorize/disconnect/test and iNaturalist OAuth authorize/disconnect/submit endpoints now declare `response_model`s, so the exported OpenAPI schema carries their real response shapes instead of an untyped body. The SPA's `integrations.ts` now derives its request/response types straight from the generated contract (shared `OAuthAuthorizeResponse`/`MessageResponse` models), removing the last hand-written DTOs in that module. No behaviour change — response bodies are unchanged.
- **API contract — typed species/eBird/seasonality responses:** The species list (`/api/species`), species search (`/api/species/search`), eBird nearby/notable (`/api/ebird/nearby`, `/api/ebird/notable`), and iNaturalist seasonality (`/api/inaturalist/seasonality`) endpoints previously returned untyped `dict`s, so the generated OpenAPI types came out `unknown`. They now declare `response_model`s (`SpeciesCountItem`, `SpeciesSearchResult`, `EbirdObservation`/`EbirdNearbyResponse`/`EbirdNotableResponse`, `SeasonalityResponse`), and the SPA's `species.ts` consumes the generated types for search, eBird, seasonality, and the detections timeline. One small shape normalisation: an eBird observation's `thumbnail_url` is now always present (null when thumbnail enrichment is unavailable) rather than conditionally omitted — the UI already treats null and absent identically.
- **Health telemetry — diagnosable critical failures:** Critical ingest-pipeline stage failures now report the exception type and stage in their anonymised `sample_context` instead of an empty `{}`. The context previously carried only the free-text error message, which the telemetry sanitiser strips (it isn't allow-listed), so fleet health data recorded *that* a stage failed but never *why*. The exception class (`error_type`) and `stage` are already allow-listed and safe, making these failures triageable across installs; the free-text error is still kept locally for the in-app Errors view. (Severity is already calibrated — `filter_*` drops are informational and excluded from health reports.)
- **Frontend toolchain:** Upgraded the UI build/test stack (supersedes the individual Dependabot bumps). Vite 8 uses the Rolldown bundler, so `manualChunks` moves to the function form (keeping `apexcharts` in its own chunk); the Docker frontend build stages move from `node:20` to `node:22` (LTS) to meet the new engine floor. TypeScript is held on the 5.9 line: TypeScript 7's native compiler is not yet supported by `svelte-check`, so that Dependabot bump is deferred. Rollback record (from → to):
  - `vite` ^5.1.4 → ^8.1.4
  - `@sveltejs/vite-plugin-svelte` ^4.0.0 → ^7.2.0
  - `vitest` ^2.1.9 → ^4.1.10
  - `typescript` ^5.4.0 → ^5.9.0 (held on 5.x; TS 7 deferred)
- **CI:** Bumped workflow actions to Node 24-capable versions (`docker/build-push-action` v6→v7, `actions/checkout` v5→v7, `actions/setup-python` v5→v6), clearing the "Node.js 20 is deprecated" runner warning on the image-build jobs.
- **Backend dependencies:** Updated the backend stack (consolidating the Dependabot bumps). The OpenAPI artifacts are regenerated for FastAPI/Pydantic's more compact schema output (no endpoint changes), and the aiosqlite test-teardown daemon-thread shim now handles both the pre- and post-0.20 threading models. Rollback record (from → to):
  - `fastapi` 0.109.2 → 0.139.0 (pulls `starlette` 0.36.3 → 1.3.1)
  - `pydantic` 2.6.1 → 2.13.4; `pydantic-settings` 2.2.1 → 2.14.2
  - `uvicorn[standard]` 0.27.1 → 0.51.0
  - `aiosqlite` 0.19.0 → 0.22.1
  - `aiomqtt` 2.0.1 → 2.5.1 (pulls `paho-mqtt` 1.6.1 → 2.1.0)
  - `alembic` 1.13.1 → 1.18.5
  - `httpx` 0.27.0 → 0.28.1; `python-multipart` 0.0.9 → 0.0.32; `slowapi` 0.1.9 → 0.1.10
  - `cryptography` 45.0.7 → 49.0.0; `aiosmtplib` 3.0.1 → 5.1.2
  - `openvino` `>=2025.4.0,<2026.0` → `>=2026.2.1,<2027.0`
  - `pytest` 8.0.0 → 9.1.1 (companion: `pytest-asyncio` 0.23.5 → 1.4.0, required because pytest 9 dropped `FixtureDef.unittest`)
  - `pyjwt` 2.8.0 → 2.13.0; `google-auth` 2.27.0 → 2.55.2; `google-auth-oauthlib` 1.2.0 → 1.4.0; `jinja2` 3.1.3 → 3.1.6 (security)
- **Telemetry worker dependencies:** Updated the Cloudflare Worker toolchain (validated with `wrangler deploy --dry-run`). Rollback record (from → to):
  - `hono` 3.12.12 → 4.12.29
  - `wrangler` 3.114.16 → 4.110.0
  - `@cloudflare/workers-types` 4.20260103.0 → 5.20260710.1
- **Setup wizard model step:** The model step now lets owners choose the classifier model, inference provider, and image execution mode from the wizard, with inline notes about the model's intended hardware/runtime profile. Hardware validation now leaves an explicit success/partial-success result instead of only showing transient progress.

### Fixed
- **Update prompt channel source-of-truth:** CI now publishes built branch versions (`dev`, `main`) and tagged releases (`stable`) to D1, and the app compares against the D1 row for the installed `APP_BRANCH`. Release-tag images identify as `stable`, so stable installs are not compared against moving branch heads.
- **Setup wizard overlay scroll:** Opening the setup wizard now locks background page scrolling; only the wizard body scrolls.
- **Setup wizard model step consistency:** The classifier-model step now follows the same pattern as the other wizard steps — it gates its content on load (no flash of empty controls), uses the shared `select-base` control styling, and its footer **Continue** commits the model/provider/execution-mode choices before advancing (the redundant in-body "Save model choices" button is gone). It is also skippable, keeps the bundled default when skipped, and disables Continue with a clear note when the chosen model still needs downloading. The on-hardware validation action stays in-step, mirroring the connection step's in-body test.
- **Duplicate update indicator:** The update-available indicator now appears only in the sidebar status cluster; the duplicate copy in the page header has been removed (the dismissible update *banner* in the main column is unchanged).
- **Frontend production logging:** Browser warning/error log contexts now strip `Error.stack` in production builds while preserving error name and message.
- **Camera status hidden on installs with no camera list:** An empty `cameras` list means YA-WAMF monitors *all* cameras, but the header camera-status indicator (and the setup wizard's camera preview) keyed only off the explicit list — so all-cameras installs saw the plain icon with no online/offline dot or count. Both now fall back to the cameras actually producing detections (via `/api/events/filters`) when the list is empty; the wizard also previews those cameras with an "Add these" shortcut to pin them.
- **Blocked species could reappear via video analysis or a slow taxonomy lookup ([#77](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/77)):** Blocking is enforced at ingest and again after taxonomy enrichment, but two paths could let a blocked species through under a *different name variant*. Auto video analysis promoted a detection using the raw video label only — it never resolved taxonomy, so a species blocked by scientific name or `taxa_id` wasn't recognised when the promoted label was a common-name/localised variant. Separately, when the live taxonomy lookup at save time failed or timed out, the re-check collapsed to raw-label matching and missed variants. Both blocked-species checks now bridge identity through the taxonomy cache (a local read that can't hang on the network) before deciding, so a species blocked under any one name/ID is caught across the ingest, save, and video-promotion paths. Abstention/unknown labels are never enriched.
- **CI:** A Cloudflare API/permission failure while publishing the built version to the update endpoint no longer fails the whole image build. The D1 version publish is best-effort for image publishing, but D1 remains the update prompt's source of truth — so the step now emits a warning instead of erroring after the images have already been built and pushed.
- **CI — version publish simplified to token-only auth:** The `publish-version` job no longer passes `CLOUDFLARE_ACCOUNT_ID`; wrangler infers the single account from the API token, removing a fragile secret from the path. Note: publishing also requires the `CLOUDFLARE_API_TOKEN` to have **no Client-IP restriction** — an IP-locked token is rejected from GitHub-hosted runners (`code 9109`, "cannot use the access token from location …"), which silently freezes the update-prompt's D1 source of truth at an old commit and nags up-to-date `dev` installs to "update". Use a token scoped to D1 Edit with IP filtering disabled.
- **CI:** The backend test job no longer hangs after a passing run. aiosqlite connection worker threads left open across pytest-asyncio event loops kept the interpreter alive after the tests finished, so the `timeout` wrapper killed the run (exit 124) despite every test passing. Test setup now marks those worker threads daemon so the process exits promptly once testing completes.
- **Security logging:** The "Authentication enabled over HTTP" warning no longer fires for internal/private clients (loopback or RFC1918/link-local addresses). In the monolithic image the bundled nginx proxies to the backend over loopback, and Docker-network services (e.g. the Home Assistant integration) poll the API over internal HTTP — none of which exposes credentials to an untrusted network. The warning is preserved for genuinely exposed cases: a public client over HTTP, or a trusted reverse proxy reporting that the real client's leg was plaintext.

## [2.12.0] - 2026-07-09

### Added
- **Telemetry:** The opt-in telemetry now reports Intel NPU availability (`intel_npu_available`), and the aggregate dashboard is public, cached, and restyled to match the app (teal brand, Instrument Sans / Bricolage Grotesque). It shows the NPU accelerator alongside GPU/CUDA/OpenVINO. Linked from **Settings → Connections → Telemetry** and [the telemetry docs](docs/features/telemetry.md); only anonymous fleet-wide aggregates are exposed.
- **Unraid (#56):** Added a Community Applications Docker template (`unraid/yawamf.xml`) and an [Unraid setup guide](docs/setup/unraid.md) so Unraid users can install the monolithic image with prefilled ports, `/config` and `/data` paths, and Frigate URL. The container runs as `nobody:users` (`--user 99:100`) to match Unraid's default appdata ownership (the image does not honour `PUID`/`PGID`), and ships no empty `Device` entry (Docker rejects `--device=''`); Intel GPU/NPU acceleration is added by attaching `/dev/dri` or `/dev/accel/accel0` manually. Verified the image starts healthy as uid 99:100.
- **BirdNET (#53):** Added a persist-time confidence floor for BirdNET-Go audio detections (`frigate.audio_min_confidence`, default `0.0`). Detections below the threshold are neither buffered for correlation nor stored, completing the configurable low-confidence filtering from the audio-history request.
- **BirdNET (#53):** Added a persisted Audio History view backed by the existing BirdNET-Go detection table, including filterable history, confidence/source/species filters, top heard species, source rollups, and hourly activity summaries separate from visual feeder detections.
- **BirdNET (#53):** Polished the audio history surfaces. The Species leaderboard now merges BirdNET-Go "heard" counts alongside camera "seen" counts with a Seen/Heard/Both toggle and surfaces audio-only species (new `GET /api/audio/species` endpoint). The Audio History view gains real charts — a daily activity timeline, time-of-day distribution, species mix donut, richer top-species cards, and per-detection spectrogram thumbnails. The dashboard audio widget adds an at-a-glance strip with today's heard count, species count, and an hourly sparkline.
- **BirdNET (#53):** The Audio History "Top heard species" cards now show a species recognition thumbnail, reusing the same lazily-loaded species imagery as the visual leaderboard and degrading silently to a placeholder when enrichment is unavailable.
- **Classifier:** Intel NPU (OpenVINO) inference provider support. The classifier can run the `rope_vit_b14` model on an Intel "AI Boost" NPU (`/dev/accel`); it was validated on Arrow Lake at f16 with top-5 output matching CPU exactly. The NPU is surfaced in classifier status, the runtime hardware probe, and the Settings device picker (shown as verified or unverified per host), and the runtime falls back to OpenVINO CPU when the NPU is requested but unavailable.
- **Home Assistant (#54):** Sidebar panel served through a Home Assistant ingress proxy. The integration registers a "YA-WAMF" sidebar entry that proxies the authenticated dashboard under `/api/yawamf/ingress`, rewrites root-relative asset and API paths, and injects the app base path so the SPA's API calls resolve through the proxy.
- **API:** Build-time OpenAPI artifact (`backend/openapi.json`) exported by `backend/scripts/export_openapi.py`, with a CI drift check so the published API contract stays in sync with the routers under `backend/app/routers`.
- **Docs & governance:** Added a documentation standard (`docs/documentation-standard.md`), a hardware-acceleration setup guide covering the Intel NPU / Intel GPU / CUDA providers, and `AGENTS.md` and `CODE_OF_CONDUCT.md` governance files.
- **CI:** Pull-request CI now runs Ruff linting over backend and Home Assistant integration Python code, and reports backend coverage with the existing floor so regressions are visible before merge.
- **Events API:** Added a documented lightweight `fields=list` event-list shape for clients that only need list-card data, preserving the full event response by default.
- **CI:** Added PR-focused backend/frontend/docs checks, CodeQL scanning for Python and TypeScript, and Dependabot updates for Python, npm, Docker, and GitHub Actions dependencies.

### Changed
- **Diagnostics:** Expected, config-driven event drops (`filter_*` — low confidence, blocked labels/species) are now recorded as informational rather than warnings, so they stay out of the health telemetry and no longer bury genuine failures on the Errors page. Health-issue reporting already excludes `info` severity, so the ~40k occurrences of normal filtering that dominated the fleet health data will drop out. Informed by the [telemetry health review](docs/reviews/2026-07-09-telemetry-health-findings.md).
- **API contract:** Generated a frontend TypeScript contract (`apps/ui/src/lib/api/generated/openapi.ts`) from `backend/openapi.json` and migrated the SPA API clients (auth, stats, events, classifier/model, backfill, settings, maintenance, media-cache, taxonomy, timezone-repair, version, Frigate connection, reverse-geocode, diagnostics, audio, leaderboard, media) to the generated response/request types, with a CI freshness check so backend contract drift reaches the SPA during review.
- **CI:** Applied a Ruff formatting baseline across the backend and Home Assistant integration, added a `ruff format --check` gate, and raised the backend coverage floor from 20% to 60% (measured ~65%) so formatting and coverage regressions fail the build. Formatting-only commits are listed in `.git-blame-ignore-revs`.
- **Classifier worker:** The progress-emit timeout is now injectable (`progress_emit_timeout_seconds`, default unchanged) and the slow-progress test waits on observed state rather than fixed sleeps, fixing a deadlock that hung the test suite when run under `coverage`.
- **Contributing:** Rewrote `CONTRIBUTING.md` to point at the `CLAUDE.md` engineering contract, target everyday work at `dev`, and list the concrete backend, frontend, docs, migration, changelog, and CI expectations for pull requests.

### Fixed
- **Home Assistant:** Video clips now play through the ingress sidebar panel. The proxy stripped `Content-Length` from streamed responses, forcing chunked transfer encoding that broke `<video>` Range/seeking, so clips failed to load and appeared as "cannot be found in Frigate". The proxy now preserves exact byte-length framing for unencoded media/snapshot bodies and treats the browser closing the connection mid-stream (seeking or switching clips) as normal instead of logging a proxy failure.
- **Home Assistant:** Lazily-loaded assets (e.g. the Leaflet map CSS/JS) now load through the ingress sidebar panel. They were requested from the site root (`/assets/…`) instead of the ingress sub-path, causing "Unable to preload CSS" errors. Vite now resolves JS/CSS asset URLs relative to the importing module (`import.meta.url`), so they load correctly under the ingress base and at the site root.
- **Maintenance:** BirdNET-Go audio detections now honour the configured retention window. Scheduled cleanup previously deleted only visual detections, so the `audio_detections` table grew without bound; it now also purges audio rows older than `maintenance.retention_days` (chunked, keyed on the audio `timestamp`) in the same cleanup pass.
- **Security:** Recording-clip HEAD response caching now runs only after feature flags, event-id validation, and event access checks, preventing cached availability from bypassing access rules.
- **Events API:** Filtered event responses now use JSON-mode serialization so timestamp fields keep the explicit UTC `Z` wire format.

## [2.11.0] - 2026-06-22

### Changed
- **Settings:** Each settings tab now has its own route. `/settings/connection`, `/settings/detection`, `/settings/notifications`, and every other tab survive a hard reload, are reachable as deep links, and reflect in the browser back/forward stack. The bare `/settings` URL canonicalises to `/settings/connection` on mount, legacy hash deep links (`/settings#integrations` from older share links and notifications) are promoted to the canonical path form once via `replaceState`, and the existing in-app routing helpers (analysis queue status, live-updates, DetectionModal's eBird configure link) now emit the new path form directly. The active tab is derived from the route prop in `Settings.svelte`, so unvisited tabs still defer their `{#if activeTab === ...}` body and the sticky save bar living in `SettingsPage` keeps unsaved-changes state visible across tab switches.

- **Classification (#33):** Final consolidation pass on the classifier inference-health refactor. `InferenceHealth` now carries the most recent recovery context (failed/recovered backend + provider, reason, diagnostics) per runtime and at the snapshot top level. The classifier-service `_last_runtime_recovery` field, the `WORKER_CIRCUIT_OPEN` / `STALE_WORK_RECLAIM` recovery-reason sentinels, the `recovery_reason` / `gpu_fallback_active` / `gpu_fallback_cooldown_remaining_seconds` fields on `live_image` health, the top-level `live_image_gpu_fallback_active` and `last_runtime_recovery` keys on classifier status, and the `last_runtime_recovery` block on `openvino_runtime` have all been removed. Every site that previously read those fields (`_gpu_restore_eligible`, `_live_gpu_fallback_health_key`, the status builders, auto-video diagnostics context, the anonymous telemetry payload, and the UI job-diagnostics store) now sources the same data from `inference_health.last_recovery` / `most_recent_recovery()`. Worker-process recoveries publish into the main-process `InferenceHealth` from `_latest_worker_runtime_recovery` so subprocess-mode installs surface the same payload. The telemetry-payload builder retains its legacy-key fallback chain so old fixtures continue to ingest.
- **Telemetry:** Anonymous heartbeats now report inference-health distributions and the most-recent recovery context. Six new fields under `payload.runtime` — `inference_health_status` (`ok` / `degraded` / `unhealthy`), `inference_health_unhealthy_runtimes`, `inference_health_degraded_runtimes`, `inference_health_total_runtimes`, sanitized `last_recovery_reason` (alphanumeric+underscore, 64-char cap), and `last_recovery_status` (`recovered` / `failed`) — let the Cloudflare telemetry worker aggregate verdict distribution and recovery-reason frequency across the install fleet. The owner-only `/dashboard` Usage view gains two panels showing per-status install counts plus the top recovery reasons.

- **Snapshots:** High-quality snapshots now prefer the full frame by default, honour the configured crop priority when a crop is appropriate, and avoid selecting tiny crops that reduce usable image quality.
- **Appearance:** New installations default to the Blue Tit colour theme; existing legacy `default` selections migrate automatically.

### Added
- **Settings:** Owners can export their configuration as a backup and import it later through Settings, including first-run-safe configuration handling and validation coverage.
- **Media:** BirdNET-Go spectrograms render in the dashboard and detection views, and matched audio clips can be requested through authenticated proxy URLs when public access is disabled.

### Fixed
- **Authentication:** Owner-equivalent access is retained when authentication is disabled, and telemetry-only settings updates no longer fail validation.
- **Deployment:** Intel GPU package-key retrieval retries and uses the current key URL, improving Docker build reliability.

## [2.10.0] - 2026-05-09

### Added
- **Evaluation:** New owner-only Model Evaluation harness at `/diagnostics/model-eval`. Auto-fetches taxonomy-verified bird images (iNaturalist primary, Wikimedia Commons fallback) for a hand-curated 50-species shared core plus a region-aware extension drawn from iNat species_counts near the configured location. Runs every installed classifier through the live `ClassifierService` pipeline, records top-1/3/5 accuracy, mean / p50 / p95 latency, abstention and high-confidence-unknown rates, shared-core vs regional breakdown, active provider, startup-benchmark drift, and `InferenceHealth` verdict. Persistent run artifacts (`summary.json`, `runtime.json`, optional `results.jsonl`, `confusions.csv`) are written under `/config/yawamf-eval/<run_id>/` so `docker exec` can read them after the UI is closed; the image cache is removed automatically at the end of each run. Sanity-check warnings flag latency drift, high abstention, low shared-core accuracy, provider fallback, incomplete installs, unhealthy `InferenceHealth`, and EU/NA region mismatches with enough numeric context to act on each one. The harness can be cancelled mid-run from the UI or via `POST /api/diagnostics/model-eval/runs/<id>/cancel`.
- **Evaluation diagnostics:** Each per-model `runtime.json` entry now carries a `gpu_diagnostic` block answering "why isn't this model on the GPU?" — registry-declared providers, OpenVINO probe state, per-model compile result + unsupported-op list, CUDA install/probe state, `/dev/dri` presence, plus a full preprocessing snapshot (input_size, color_space, resize_mode, mean/std, interpolation) and the ONNX artifact's producer/version/sha256. Catches color-space and normalization mismatches that otherwise look identical to GPU precision bugs.
- **Models:** Five new bird-only classifiers from the Birder project (eu-common dataset, 707 species), self-converted to ONNX via the procedure documented at `docs/conversions/birder-model-conversion.md` and published to the YA-WAMF models release with SHA256 verification:
  - `moganet_s_eu_common` — **iGPU validated**, 257ms iGPU. Best CPU/GPU agreement of any new candidate (top-5 overlap 5/5).
  - `convnext_v1_tiny_eu_common`, `regnet_y_8g_eu_common`, `uniformer_s_eu_common` — `advanced_only` CPU-only architectural alternatives kept as harness comparators (each fails on Intel iGPU in a distinct way: V1 BatchNorm precision drift, RegNet logit-rank divergence, UniFormer NaN).
  - The ConvNeXt-V2-Tiny eu-common, DaViT-Tiny IL-ALL, and MViT-v2-Tiny IL-ALL candidates were also converted and probed but removed before adoption — each was strictly dominated by an existing registry entry. Conversion procedure and dominance reasoning recorded in `docs/conversions/birder-model-conversion.md` and the GitHub release notes.
- **Models:** The four Birder eu-common ONNX artifacts and a refreshed `eu_medium_focalnet_b` carry SHA256, labels_sha256, and (where applicable) weights_sha256 in the registry, verified on download via the existing `_verify_checksum()` machinery.
- **UI:** Model Manager picker now groups classifiers by recommended-use category — "Fast on Intel GPU", "Balanced (CPU)", "Highest accuracy (CPU)", "Architectural alternatives (CPU)", "Built-in fallback" — using native `<optgroup>` so screen readers and keyboard nav work without extra plumbing. A category hint renders below the picker for the active selection.
- **UI:** BirdNET-Go matched audio is now playable inline in the detection modal. The modal already showed the matched spectrogram; this release adds playback driven by a hidden `<audio>` element, surfaced via a custom overlay: a centered glassmorphic play/pause button, an amber playhead cursor with a trailing gradient, a tabular-numeral time pill, and click-anywhere-on-the-spectrogram-to-seek. Range pass-through in the new `/api/audio/clip/<birdnet_id>` proxy lets the browser scrub natively. Native HTML5 controls intentionally hidden in favour of the custom overlay.
- **Roadmap:** New entries for HAOS add-on (issue #49) and the model evaluation harness completion notes.
- **Roadmap:** Clarified the next implementation target as the feeder-specific model evaluation harness, including the recommended script shape, manifest fields, output files, and test expectations.
- **Evaluation (feeder harness):** Added `backend/scripts/eval_feeder_model_harness.py`, a feeder-specific model evaluation harness that runs labeled real-world feeder images through `ClassifierService`, compares installed model IDs and crop modes, restores active model/crop settings after each run, and writes `summary.json`, `results.csv`, and `failures.csv`. The summary tracks top-1/top-3 accuracy, per-species breakdowns, inference timing, crop diagnostics, and high-confidence `Unknown` top-1 outputs as a distinct failure mode. Auto-bootstraps a manifest from the live SQLite DB + media cache when `--manifest` is omitted; auto-discovers installed classifier models when `--models` is omitted; supports `expected_aliases` / `acceptable_labels` for cross-locale common-name matching; reports top-K abstention counts and labels.
- **Deployment:** The monolithic image now includes `backend/scripts` under `/app/scripts` so evaluation harnesses can be run inside a pulled live container against its installed models, database, and media cache.

### Changed
- **Models:** `convnext_large_inat21` and `rope_vit_b14_inat21` registry entries no longer claim `intel_gpu` support. Live harness retest 2026-05-08 on OpenVINO 2025.4.1 confirmed the historical failure modes are still real on current OpenVINO: ConvNeXt's depthwise-conv precision degradation collapses top-1 accuracy 66.8% → 32.7% on iGPU even though compile succeeds; RoPE-ViT's startup self-test catches NaN logits and falls all the way back to ONNX Runtime CPU. Listing `intel_gpu` was wasting a compile attempt every model load. Both stay CPU-only with current-dated evidence in `tests/test_model_openvino_gpu.py`.
- **Models:** `medium_birds`, `small_birds`, and `bird_crop_detector_accurate_yolox_tiny` registry entries now declare `intel_gpu` support and the variants got accompanying entries in the GPU validation matrix.
- **Models (family activation):** `model_manager.activate_model()` now resolves family models (medium_birds, small_birds) to their installed eu/na variant before validating the install. Previously the validator looked for `model.onnx` at the family parent dir, which never exists, so family models were silently rejected by the eval harness despite working in production via `get_active_model_spec()`. Both code paths now use the same family-aware resolution.
- **Classification (#33):** Live-image GPU fallback status now derives its active/cooldown state from `InferenceHealth` instead of a separate classifier-service monotonic timestamp. Existing `gpu_fallback_active` response fields remain as compatibility aliases, and runtime recovery records now carry the exact failed runtime key that triggered fallback.
- **Classification (#33):** Successful startup runtime benchmarks now seed the matching `InferenceHealth` latency baseline, and latency-based health verdicts only use low-pressure inference samples. Load-affected samples remain visible in telemetry but are excluded from baseline drift decisions so queue pressure does not masquerade as a slow runtime.
- **Telemetry:** Runtime telemetry now reports OpenVINO GPU fallback from the classifier's explicit live-image fallback status instead of treating any runtime recovery as GPU fallback.

### Fixed
- **Evaluation:** Five issues surfaced by the first live model-eval harness run — Wikimedia REST API 403s caused by missing `User-Agent` header (fallback now works, image fetches no longer iNat-only); progress label froze on `activating <model>` for the entire model evaluation phase (now refreshes every 2 s with `<model> N/M images`); family models surfaced silently as missing rather than appearing in `skipped_models[]` with reason; bundled mobilenet incorrectly flagged `incomplete_install` for missing `model_config.json` (which by design ships without one); iNat duplicate-taxa nodes for the same species (e.g. Pica pica resolving to taxa 891696 vs 17550 through different code paths) caused correct predictions to score as wrong — scoring now matches by taxa_id OR case-folded scientific/common name, and panel deduplication is by both taxa_id and scientific_name.
- **Evaluation:** First-run iNaturalist throttling cut the species panel by ~30% on the initial harness run. Panel build now uses the DB-cached `taxonomy_service.get_names()` so subsequent runs skip iNat entirely, and first-run lookups are paced 250 ms apart to stay under the anonymous rate limit. Per-prediction iNat fallback for non-panel labels (the dominant runtime cost in v1) was removed entirely — predictions that don't match panel species keep `taxa_id=None` and don't affect accuracy scoring.
- **Classification:** Video analysis now treats model-emitted abstention labels as non-species evidence rather than species candidates. Per-frame video aggregation skips frames whose top label is `Unknown` / `Unknown Bird` / `No detection` / `No data` / similar exact abstention labels, removes hidden unknown classes from the final top-K list, ignores abstention-labeled analysis frames when selecting stored top frames for HQ snapshot reuse if known-species frames are available, and refuses to promote or publish automatic abstention video results as usable species labels even when confidence is high.
- **Classification:** Live snapshot, historical backfill, manual snapshot reclassification, and snapshot fallback paths now discard model-emitted abstention labels before choosing a species. If `Unknown`, `No detection`, `No data`, or similar labels appear ahead of a concrete species, YA-WAMF now evaluates the lower-ranked concrete candidate instead of saving or promoting the abstention as a useful classification.
- **Models/UI:** Incomplete classifier installs are no longer treated as activatable models. The backend now marks installed models with `ready` / `reason`, rejects activation when the runtime model, labels, or required config sidecar is missing, falls back to the bundled classifier if a stale active model is incomplete, and the Model Manager shows a repair-needed state with a `Repair download` action so users can fix the install from the UI.

## [2.9.15] - 2026-05-05

### Added
- **UI:** Recent Audio dashboard widget now animates list updates instead of swapping in place. Each entry is keyed by `birdnet_id` (with a stable composite fallback) and wrapped in `animate:flip` plus directional `fly` transitions so new BirdNET-Go detections fly in from the top, intermediate items slide via FLIP, and the bottom entry falls off as the rolling window evicts it.
- **UI:** Detection modal now embeds the BirdNET-Go spectrogram for the audio detection matched against the visual one. Audio context is auto-fetched on open whenever the detection has any audio info; the matched audio entry is selected by species match against `audio_species` (when audio_confirmed) and otherwise by smallest absolute time offset. The spectrogram renders as a full-width image inside the audio match card with a caption strip showing species, confidence, and time offset. The existing "Show audio context" expand control still toggles the full per-entry list and shares the auto-loaded data.
- **Settings:** Shared `_primitives/SecretInput` primitive applied to every saved-secret field across the Settings tabs (LLM API key, owner password, MQTT password, iNaturalist client ID/secret, eBird API key, BirdWeather token, Discord webhook, Pushover user/token, Telegram bot token/chat ID, Gmail/Outlook OAuth client secrets, SMTP password). When a secret is saved the input is grayed out, shows the standard 'Saved' tick badge inside the field, and uses the redacted placeholder. The previous mix of free-floating SecretSavedBadge components above SettingsInputs is gone.
- **Backfill:** Async detection backfill now auto-chains a same-period weather backfill on successful completion via a new shared `_start_weather_backfill_async` helper. The chained job uses `only_missing=true` to keep work cheap when weather data is already populated, runs through the standard maintenance lane gate, and skips silently if the lane is busy or another weather job is already running. The detection job's success state is unaffected by the weather job — chain failures are logged.
- **Telemetry:** Anonymous usage telemetry now records the configured/active inference provider, active backend, model runtime, execution mode, crop-detector tier, GPU/runtime capability flags, and deployment image metadata. Settings → Connection → Telemetry now shows the same runtime/device snapshot before it is sent, and the Cloudflare dashboard breaks the new fields down in the Usage view.
- **Telemetry:** The Cloudflare telemetry Worker now serves a Basic-Auth protected `/dashboard` with Usage and Health views backed directly by D1 aggregate queries. It shows install counts, active versions/models, feature adoption, country distribution, health severity/component summaries, and top recurring health issue fingerprints without adding Pages, KV, R2, or any paid service.
- **Telemetry:** Added a separate opt-in Anonymous Health Diagnostics channel backed by its own Cloudflare D1 database. YA-WAMF now groups warning/error/critical backend diagnostics into sanitized issue fingerprints once per day, excluding media, camera names, event IDs, URLs, credentials, raw logs, and detection content. The telemetry worker exposes `/health-issues` for ingestion and `/stats/health-issues` for aggregate debugging summaries.
- **Backend/UI:** New internal `birdnet_url` and browser-facing `birdnet_external_url` settings (Settings → Integrations → BirdNET-Go) plus a backend `GET /api/audio/spectrogram/{birdnet_id}` proxy. The Recent Audio dashboard widget now renders the BirdNET-Go spectrogram PNG (cached 1d server-side, 30d immutable upstream) as a faded background behind each audio card using the backend/internal URL, while user-clickable BirdNET-Go links use the external HTTPS URL when configured. The widget header also gains a small "BirdNET-Go ↗" badge linking to the configured web UI in a new tab. The audio detection schema now exposes `birdnet_id` extracted from the MQTT payload (`detectionId` / `id` / `detection_id`).
- **Backend/UI:** Per-camera **role** setting (`feeder` or `nest`) plus a global `nest_dedupe_minutes` window. When a camera's role is `nest`, the event processor skips the save+notify path for any new detection whose species was already recorded on that camera in the last N minutes (default 30). Stops a continuously-present nesting bird from inflating detection counts, leaderboard rankings, and notifications. Settings → Connection now exposes a feeder/nest segmented picker per selected camera and a dedupe-window input that appears once at least one camera is in nest mode. The page-header `CameraStatus` popover shows a Feeder/Nest tag next to each camera so you can see at a glance how each one is configured.
- **UI/Backend:** Settings → Location now reverse-geocodes the configured latitude/longitude through a new `GET /api/location/reverse-geocode` endpoint (Nominatim, in-memory cache rounded to 2 decimal places). Manual mode no longer asks the user to type state and country — those values are derived from the coordinates and persisted on save, and the resolved place is shown inline beneath the lat/lon fields. The iNaturalist default place guess auto-populates from the same lookup the first time it is empty.

### Changed
- **Settings:** Comprehensive Settings tab cleanup pass.
  - **Connection:** Removed the redundant Test MQTT button (the BirdNET MQTT pipeline test still lives in Integrations). MQTT port moved out of the Tuning advanced overflow and placed inline with the MQTT broker — port is a standard required setting and does not belong behind an Advanced toggle. The connection Tuning advanced section is now hidden entirely when full-visit recording clips are disabled.
  - **Detection:** The bird crop detector tier picker moved out of the DetectionSettings Advanced overflow and into ModelManager itself, rendered as the same prominent dropdown selector used for the main classifier model lineup. Crop detector model selection and main model selection now share one consistent control. Trust Frigate Sublabel and Write Frigate Sublabel toggles, plus the auto-video tuning controls, are now folded into a single 'Advanced fine tuning' overflow on the Fine Tuning card. Execution Mode and Runtime diagnostics are now folded into a single Advanced overflow on the Inference Provider card. Each settings card now has at most one Advanced section.
  - **Notifications:** Global Notification Filters now uses the shared `SettingsCard` primitive instead of the bespoke amber-gradient section, and the inline pill-style 'Advanced ON/OFF' toggle in the delivery-policy block is replaced with the standard `AdvancedSection` primitive.
  - **Data:** Removed the standalone Diagnostics card from the Data tab. The Health tab in the page header already exposes the same diagnostics workspace.
  - **AdvancedSection primitive:** No longer persists open/closed state to localStorage. Every Advanced overflow starts closed on each fresh load of the settings page so primary controls are always the first thing the user sees.
- **UI:** Owner diagnostics now live as a first-class Settings → Health tab. Legacy `/settings/errors` and `/notifications/errors` routes canonicalize to `/settings/health`, and visible copy now presents the surface as health diagnostics rather than an errors page.
- **UI:** Diagnostics were removed from Notifications; the Notifications page only contains Notifications and Jobs.
- **UI:** Recent Audio on the dashboard now requests up to 10 BirdNET-Go detections instead of 5 so the card better uses the available dashboard space.
- **UI:** Page refresh actions now live in the shared page header as an icon button inline with camera status, notifications, and settings. Dashboard, Events, Species, Settings, Jobs, and Errors register their own refresh handlers, and duplicate in-page refresh buttons were removed where the header action now covers the same work.
- **UI:** About restores the application icon below the global page header controls and above the tagline, and the Species page no longer repeats the leaderboard title/count row now covered by the shared page header context.
- **UI:** Auto/manual location toggle replaced with a clearer two-card segmented control ("Auto-detect" / "Manual entry") explaining what each mode does.
- **UI:** Sidebar collapse/expand now lives at a single consistent slot at the very bottom of the sidebar (replacing the absolute-positioned chevron in the brand block and the separate collapsed-only expand row).
- **UI:** Notifications, language, and theme are now a single inline icon row at the bottom of the sidebar (above the collapse toggle) instead of three full-width rows. `LanguageSelector` gained a `compact` prop that renders icon-only with a tooltip carrying the current language name. The expanded sidebar now matches the visual rhythm of the collapsed sidebar instead of being noisier than it.
- **UI:** New page header chrome rendered above every route (Dashboard, Events, Species, Notifications, Settings, About). Left side shows the page title; right side shows a camera-status icon (configured camera count plus an online/mixed/offline status dot, with hover popover listing each camera with a live frame thumbnail from the existing `/api/frigate/camera/{name}/latest.jpg` endpoint), the existing notifications bell, and a settings cog. Modeled on the BirdNET-Go layout. Per-page titles in `SettingsPage`, `About`, `Events`, and `Notifications` were removed so they no longer duplicate the global header.
- **UI:** Sidebar utility row is now language + theme + collapse — the notifications bell has moved to the page header, the collapse toggle has moved into the utility row, and the dedicated bottom collapse slot has been removed.
- **UI:** AI settings tab now uses the full Settings page width again — the usage table has five columns and was being cramped by the new `max-w-3xl` cap applied in 2.9.14.

### Removed
- **Settings:** The AI Diagnostics Clipboard feature has been removed. Both the Debug-tab toggle and the floating copy-bundle button rendered above the detection and species-detail modals are gone, along with the supporting `aiDiagnostics` collection helpers (markdown style sampling, computed-style probes) and the `ai-diagnostics-enabled-changed` localStorage/CustomEvent bridge between the Settings page and open modals.
- **Settings:** The owner-only iNaturalist preview toggle has been removed. The submission panel is again gated only on `inatConnectedUser`. The Debug-tab toggle, its apply-pending status row, the apply button, the inat preview hint, and all `inatPreview` query/localStorage paths in DetectionModal are gone.

## [2.9.14] - 2026-05-03

### Changed
- **UI:** BirdNET source mapping section in Settings → Integrations has been simplified — per-camera input and source-discovery dropdown now align cleanly, the recently-detected BirdNET sources list shows full source names with a compact relative-time label (e.g. `2m ago`), fades older entries, and supports click-to-add directly into the first configured camera mapping. The previous nested cards-within-cards layout is now flat with hairline dividers.
- **UI:** Settings and About pages now use the same `max-w-7xl` page width as Dashboard, Events, Species, and Errors so the page chrome (header, sticky save bar, tabs) is consistent across the app. All Settings tabs use the full page width.
- **UI:** Location card in Settings → Integrations now includes a map preview that pins the currently-configured latitude/longitude (manual or auto-detected). Reuses the existing Leaflet `Map` component already used by Species range maps and the detection modal — no new dependency.
- **UI:** Sidebar brand mark now sits above the title in a vertical stack (matching the HarborWatch pattern) and uses a new `BrandMark` component with a `srcset` of 32/180/192/512 px PNG assets, so the browser picks the sharpest source for the device pixel ratio at both the collapsed (40 px) and expanded (64 px) sidebar widths instead of always scaling the 192 px PWA icon.

### Fixed
- **Maintenance (#33):** Batch analyze-unknowns now uses admission control instead of queueing every eligible historical detection at once. Each run accepts at most 50 maintenance video jobs, defers when maintenance work is already queued or active, and reports the batch limit / remaining candidate count so large backfills drain in visible batches without flooding the video-classifier queue.
- **Maintenance (#33):** Batch analyze-unknowns now scans only the newest 200 unresolved unknown detections per run, ordered by detection time, instead of walking the entire historical unknown backlog. This keeps dirty databases with stale old Frigate events from spending minutes prechecking obsolete rows before reaching the current backfill batch. The issue-33 fixture harness threshold now matches the bounded 50-job maintenance queue cap.
- **UI (#47):** Snapshot fallback reclassification now uses a snapshot-scanning visual instead of the video film-reel animation. When a clip is unavailable and YA-WAMF classifies the saved snapshot, the overlay shows the snapshot being scanned so the in-flight state matches the work actually being performed.

- **Classification (#33):** OpenVINO Intel GPU → CPU fallback now also triggers on repeated maintenance video timeouts and snapshot-fallback `background_image_lease_expired` errors, not just live lease expiries. Previously an unhealthy Intel GPU was only caught by the live-image signal, so during overnight batch-analyze runs (no live Frigate traffic) the batch could spend hours timing out every item at 180 s and failing snapshot fallback with a background-image lease expiry each time, because nothing upgraded the signal into a model hot-swap. Signals from all three sources now feed the same fallback-threshold counter, so the batch self-heals onto CPU after a few bad items instead of stacking orphaned GPU work.

- **Classification (#33):** Live snapshot classification now records provider/model context when live classifier work is abandoned, emits a distinct `classify_snapshot_lease_expired` diagnostic for classifier lease expiry, and temporarily falls back from the in-process OpenVINO Intel GPU path after repeated live lease expiries so healthy Frigate MQTT traffic is less likely to collapse into `classify_snapshot_timeout` / `classify_snapshot_overloaded` drops. The issue-33 soak summary also tracks live-image abandoned work and classify-snapshot timeout/overload deltas directly.
- **Classification (#33):** Fresh live MQTT events now get a larger default live-classifier queue budget before YA-WAMF drops them as `classify_snapshot_overloaded`. The previous 2-second cap was too short for the CPU/OpenVINO live path seen in the April 23 reproducer, so fresh events could be discarded while they still had ample stale-time budget remaining.
- **Classification (#47):** Auto video classification no longer aborts with `event_not_found` when the Frigate event API is transiently unavailable but the clip is already cached locally. The precheck now checks `media_cache` first and proceeds with the cached clip when one is present, so detections that would have stayed `Unknown Bird` can still be promoted by video analysis.
- **Classification (#47):** Manual reclassify (snapshot strategy) now checks the local snapshot cache before fetching from Frigate. Previously, if the Frigate event was not reachable at reclassify time, the endpoint returned 502 "Failed to fetch snapshot from Frigate" even when a cached snapshot was available in YA-WAMF. The fix resolves both the auto-classify and manual-reclassify failure modes reported in the issue.
- **Classification (#47):** Auto video classification and manual video reclassify now also accept a cached *recording/full-visit* clip as sufficient to run video analysis when Frigate's event API returns `event_not_found`. Previously the precheck bypass only checked the Frigate event-clip cache, so detections where YA-WAMF had only the recording clip cached (the clip the user can still play in the UI) would silently degrade to snapshot-only classification with the video-analysis UI still on screen. With a recording clip available, video classification now runs as intended instead of falling back to a less accurate snapshot guess.
- **UI (#47):** When a reclassification job genuinely has no clip available and the backend downgrades from video to snapshot mid-flight, the in-flight overlay no longer keeps its film-reel "video analysis" framing. The backend now emits a `reclassification_strategy_changed` SSE event and the overlay swaps in a clear "Classifying from snapshot" banner with the reason (clip not retained, event not found, etc.). Completed detections that were classified from a snapshot because video analysis failed also get a matching notice in the detection modal, so the lower confidence of the result is self-explanatory.
- **Classification (#47):** Auto video classification now schedules one delayed retry when the precheck aborts with `event_not_found` *and* no clip is cached locally yet, but the user has full-visit recording clips enabled. The recording-clip auto-fetch is asynchronous and often arrives a few seconds after auto-classify first runs; the previous behaviour gave up after ~6 seconds of precheck retries and permanently marked the detection failed. The new path waits 60 seconds and retries the precheck once. The retry is bounded (one attempt only), gated on circuit-open status and service-running state, idempotent per event id, cancelled on `stop()` / `reset_state()`, and skipped when an MQTT-driven attempt is already running for the same event. The interim state keeps DB status as `pending` (no `failed` mark, no `_record_failure`, no `_auto_delete_if_missing`, no `reclassification_completed` broadcast) so the UI overlay does not dismiss prematurely.
- **Classification (#47):** Auto video classification now listens for late-arriving recording clips in the media cache and re-queues stranded detections that previously failed with `clip_not_found`, `clip_not_retained`, `event_not_found`, or `clip_unavailable`. This closes the race where the 60-second precheck retry could still fire before the full-visit recording slice finished caching, leaving the detection permanently failed even though the recording clip arrived a minute or two later.
- **UI (#47):** Detection modal now surfaces the gated-promotion case where video classification ran successfully but auto-promotion was withheld because the score sat below the configured minimum-confidence floor (`apply_video_result` raises the unknown-upgrade floor to `max(0.10, min(min_confidence, threshold))`). Previously the thumbnail kept showing "Unknown Bird" while the modal's Video Analysis card showed the correct species, with no explanation. A new indigo notice now spells out the gating in plain language and offers a single-click Reclassify button that runs the manual path (which legitimately bypasses the auto floor as an explicit owner action). The notice never appears for blocked-species results — those have their own existing label — and never appears in read-only / public-access views where reclassify is unavailable.
- **Translation (#46):** Recent Audio panel was still showing localised BirdNET-Go names for users running the frontend in English when the audio buffer's `scientific_name` lookup did not yield a `taxa_id`. This happened in two cases: (a) BirdNET-Go did not publish `ScientificName` and the iNaturalist lookup at ingest time could not resolve the locale `comName`, so the cache row was saved with `taxa_id = NULL`; (b) `add_detection` stored the non-Latin `comName` itself as `scientific_name` because `get_names()` returns the original query string when iNat fails. The audio localizer now falls back through two additional resolution paths when the scientific-name lookup misses: it tries `taxonomy_cache.common_name` (matches if the canonical English name was already cached during a prior visual classification) and then `taxonomy_translations.common_name` in any locale (matches if the visual path has cached the localised name). No iNaturalist round-trips and no schema changes — both fallbacks read tables that are already populated by the visual flow.

### Added
- **Classification (#33):** Added additive inference-health telemetry for classifier runtimes. `/health` now includes an `inference_health` snapshot keyed by backend/provider/model, with recent outcomes, latency percentiles, verdict, and cooldown state. This is Phase 1 of the classifier health refactor and does not change routing or fallback behavior.
- **Notifications (#48):** Settings now expose a species filter mode with "No species filter", "Block selected species", and "Only selected species" options. The filter uses the taxonomy-aware species picker so users can select birds by common name, scientific name, or taxonomy ID instead of maintaining raw text labels.
- **Notifications:** Notification species filtering now supports structured allow-list and deny-list entries keyed by taxonomy identity (`taxa_id` + scientific/common name) in addition to the legacy string whitelist. A blacklist match always wins over a whitelist match. Taxonomy identity is resolved in the notification orchestrator via `taxonomy_service.get_names` and passed through to `_should_notify`, so species that share a common name across locales (e.g. "Robin") can now be filtered unambiguously. Existing `notifications_filter_species_whitelist` continues to work unchanged.

### Added
- **i18n:** Comprehensive translation pass covering ~300 previously English-only strings across all 8 non-English locales (de, es, fr, it, ja, pt, ru, zh). New keys cover the Errors/diagnostics page (subsystem cards, metric labels, summary prose, bundle management), LLM settings, eBird export labels, location fields, security warnings, and miscellaneous UI strings. All summary functions in `Errors.svelte` (`overallSummary`, `eventPipelineSummary`, `mqttSummary`, `liveClassificationSummary`, `backgroundSummary`, `dispatcherSummary`, `startupSummary`, `refreshedAgoText`) now resolve through the i18n store at runtime. Hardcoded English strings replaced in `Errors.svelte`, `DetectionSettings.svelte`, `ModelManager.svelte`, `About.svelte`, `Footer.svelte`, `DetectionModal.svelte`, `ErrorBoundary.svelte`, and `ReclassificationOverlay.svelte`.

### Changed
- **Deployment:** Added a dedicated `ghcr.io/<owner>/yawamf-monalithic-rpi` ARM64 image line for Raspberry Pi 4/5 monolith installs, plus a new Raspberry Pi setup guide covering image overrides, hardware expectations, and current support limits.
- **AI Models:** Added an experimental `accurate` bird-crop detector tier wired for YOLOX-Tiny alongside the existing default `fast` detector. Settings now expose crop-detector tier selection, the model manager lists both managed crop-detector artifacts, and the backend falls back from `accurate` to `fast` automatically if the accurate detector is unavailable.
- **UI:** Detection details now include an owner-only snapshot repair overlay launched from the existing camera icon on the media panel. YA-WAMF persists a bounded set of HQ snapshot candidates per detection, shows a staged picker for `Full snapshot`, `Frigate hint crop`, `Original Frigate crop`, and a full candidate-frame grid sourced from every generated candidate, and applies the selected candidate only when the user presses `Save snapshot`.

### Changed
- **Deployment:** `docker-compose.monolith.yml` now supports `YAWAMF_MONALITHIC_IMAGE` as an optional full image-name override, making it easier to switch between the standard monolith image and the Raspberry Pi image without editing the compose file.
- **Backend:** ARM64 installs now use CPU `onnxruntime` while x86-64 keeps `onnxruntime-gpu[cuda,cudnn]`. Intel GPU runtime setup in both Dockerfiles is now skipped automatically on non-`amd64` builds.
- **Classification:** Snapshot and high-quality snapshot cropping now share a global `bird_crop_source_priority` setting. The default remains `frigate_hints_first`, but owners can now choose `crop_model_first`, `crop_model_only`, or `frigate_hints_only` while still respecting the configured crop-detector tier whenever the model path is used.
- **Classification:** Automatic video classification now prefers a cached recording/full-visit clip when one is already available, matching the manual reclassify path more closely. If the cached recording clip is invalid, YA-WAMF now falls back to the normal Frigate event clip instead of failing the auto-video run.
- **Classification:** High-quality snapshot generation now scores and persists multiple candidate frames per detection instead of committing only a single derived frame path. Candidate metadata includes source mode, clip variant, classifier score, and crop confidence, and stale candidate cache artifacts are cleaned up when a detection’s candidate set is replaced.
- **Classification:** HQ snapshot generation now reuses the top-ranked frames from a completed video analysis run instead of sampling arbitrary frames. The video classifier now records up to eight top-scoring frames per clip (with their timestamps, scores, and labels) into a new `video_classification_top_frames` table. When generating HQ snapshot candidates, the service loads those stored frames first and passes them as preferred frame indices to the crop model, so the model operates on frames already confirmed to contain a visible bird. If no stored frames exist the previous generic sampling logic is used unchanged.

### Fixed
- **Translation (#46):** Dashboard "Recent audio" and the audio-context endpoint now resolve the displayed species name at response time via `taxonomy_cache` rather than returning the raw BirdNET-Go `comName`. Previously, if BirdNET-Go was configured for a non-English locale (e.g. Russian) the name it published leaked through unchanged into the YA-WAMF UI — so a user running the frontend in English still saw Russian species names in the audio feed. The new transform mirrors the species/leaderboard fix (`77524a9`): for each detection we look up `taxa_id` from the stored `scientific_name`, then use `get_canonical_english_name` (English) or `get_localized_common_name` (non-English) to produce the display name. Falls back to the stored species string when no taxa_id is available. No schema changes.
- **Classification:** Birds-only ONNX export script (`scripts/export_birds_only_model.py`) now translates timm's `pretrained_cfg['crop_mode']` into our `preprocessing.resize_mode` (`squash`→`direct_resize`, `center`/`border`→`center_crop`). Previously `resize_mode` was hardcoded to `center_crop` for every exported model — so models whose upstream training recipe used `squash` (typical for EVA-02 and CLIP-init ConvNeXt variants) would be served at inference with a center-crop pipeline that produces different pixel content than the one they were trained on. New models exported through this script now inherit the correct resize mode; existing per-model `model_config.json` files in the release are unchanged and still win when installed.
- **Classification:** ONNX and OpenVINO classifier `_preprocess` paths now honor `preprocessing.color_space: "BGR"` by reversing the channel axis before normalization. Previously this field was only honored by the crop-detector path — a classifier model trained on BGR tensors would silently receive RGB pixels and produce garbage predictions with no warning. All currently-registered classifiers declare `RGB`, so this is a defensive fix against future BGR-trained models rather than a live regression.
- **Maintenance (#33):** `MaintenanceCoordinator` now tracks capacity per-kind instead of sharing a single global slot. Previously a long-running `video_classification` holder could block `backfill`, `weather_backfill`, `taxonomy_sync`, `timezone_repair`, and `analyze_unknowns` for hours and produced a 962-deep pending queue in v2.9.13-dev diagnostics. Added an optional overall `total_max_concurrent` safety cap (default `3`) so many kinds running at once cannot saturate the DB pool, plus a `per_kind_capacity` override map for per-kind tuning.
- **UI (#33):** Terminal jobs (`completed`/`failed`) can no longer be revived by a late SSE `running` event that arrives after the terminal one — an ordering race was letting historical jobs reappear in the active list. Added a long-running-kind override so backfill, weather-backfill, and reclassify-batch jobs are no longer marked stale after the short default idle window.
- **UI (#33):** Deploy-refresh popup no longer fires on SemVer build-metadata changes (e.g. `2.9.13-dev+a127aa9` → `2.9.13-dev+b58f6f5f`). Per SemVer §10 build metadata is ignored for precedence; the health watcher now strips the `+build` suffix before comparing versions.
- **UI (#33):** Backfill status polling now adapts to activity. When no backfill job is running the store falls back to a 30s idle cadence instead of hammering `/api/backfill` every 2s (~60 GETs/min of noise). Refresh throws are caught so the polling loop recovers on the next tick instead of silently dying.
- **Backend (#33):** `db_pool.acquire_wait_max_ms` is now a windowed maximum over the last N samples instead of an all-time peak, so a single transient spike no longer keeps the health panel red forever.
- **Backend (#33):** `ModelManager` now deduplicates the "unsupported provider" warning per `(model, providers)` tuple so repeated model loads do not flood logs with identical warnings.
- **Classification:** Auto video classification no longer promotes `Unknown Bird` to a species on very weak scores. Unknown-label upgrades now respect the configured classifier floor, so low-confidence video guesses stay `Unknown Bird` instead of auto-overriding to an implausible species.
- **Classification:** Auto video promotion is now less brittle for low-confidence primary detections. When the current primary label never cleared the main threshold, a stronger video result can now replace it without needing to clear the full primary threshold, while the existing Frigate sublabel disagreement guard remains in place.
- **Classification:** HQ snapshot candidate metadata now records the actual clip variant used (`event` vs `recording`) instead of inferring it from global settings, and recording-clip fallback can reuse an already-cached full-visit clip without depending on DB-backed helper state.
- **UI:** Snapshot picker strings are now defined in the locale bundles instead of relying on inline English defaults, and the picker once again exposes `Generate HQ snapshot` with an in-place refresh of the saved candidate list after generation.
- **UI:** Snapshot generation no longer looks like a no-op when a detection produces only full-frame and Frigate-hint candidates. The picker now shows all generated candidate frames and explicitly explains when no model-crop frames were found for that detection.

## [2.9.13] - 2026-04-16

### Fixed
- **UI:** Detection detail modal media panel no longer collapses to a thin strip on mobile. The `aspect-video` panel had no `flex-shrink: 0` constraint, so the flex algorithm compressed it when the detail panel's content was tall. Added `shrink-0` to prevent this; the image/video area now correctly fills its 16:9 height on all mobile viewports.

## [2.9.12] - 2026-04-16

### Fixed
- **UI:** High-confidence audio-confirmed detections on detection cards now correctly show the musical note badge instead of a tick. The tick was shown when `audio_confirmed` was true and score exceeded 0.7; it now uses the same musical note icon as lower-confidence audio matches.

## [2.9.11] - 2026-04-16

### Changed
- **UI:** Audio match badge on detection cards and the audio section icon in detection details now use a musical note icon instead of a microphone.

## [2.9.10] - 2026-04-16

### Changed
- **UI:** Species leaderboard Most Active highlight card now has the same icon-badge treatment as Rising and Most Recent: a bar-chart icon in an emerald-tinted pill replaces the old blurred background image.
- **UI:** Rank medals in both Top Performers cards and the Full Rankings table now use 🥇🥈🥉 emoji instead of custom SVG rosette badges, keeping the two sections visually consistent with each other.
- **Docs:** Comprehensive documentation review — BirdNET-Go GitHub/Docker URLs corrected, legacy split deployment marked with warnings throughout, new MQTT Broker Setup guide, expanded Frigate integration and Deep Video Analysis pages, internal dev plans folder removed.

### Fixed
- **UI:** The Errors tab badge in the notification drawer no longer increments for SSE disconnections that happened while the browser tab was in the background. These events are transient, self-healing, and not user-actionable. All events remain preserved in the full diagnostics export; only the nav-badge count is filtered.
- **UI:** Cloudflare/nginx gateway errors (HTTP 502/503/504) during container startup no longer appear in the Errors diagnostics tab. These are transient infrastructure events that self-heal on the next poll tick. The raw HTML error page body is no longer stored as the error message; the logger still records them for traceability.

## [2.9.9] - 2026-04-16

### Changed
- **UI:** Species leaderboard bar chart (detections over time) no longer shows a legend. The series composition is already visible on hover; the legend was redundant visual noise alongside the chart itself.
- **UI:** Species leaderboard Rising and Most Recent highlight cards are redesigned. The blurred detection-image background is replaced with a clean icon badge (trending-up arrow for Rising, clock for Most Recent) against a tinted card background, improving legibility across all images.
- **UI:** Full Rankings table in the species leaderboard now uses the same rosette SVG badges (gold / silver / bronze) as the Top Performers section. The previous medal emoji approach was visually inconsistent between the two tables.
- **UI:** Video player now uses the browser's native `<video controls>` element directly. Plyr has been removed. All existing UI state — the playing/paused/buffering/ended status pill, the Preparing overlay, share link buttons, download button, and share manager — continues to work via native `HTMLVideoElement` events. Autoplay with muted fallback is handled programmatically; the `autoplay` HTML attribute is not used to avoid browser autoplay-policy races.

### Fixed
- **UI:** Detection modal bottom overlay (species name, sub-name, play button) no longer bleeds over the detail panel on mobile. `overflow-hidden` is applied to the media panel so the `absolute`-positioned overlay is clipped to the video area. Long species names are also truncated to keep the play button on-screen at all times.
- **UI:** Full-visit clip availability now self-corrects shortly after a detection is created. When a probe returns `available=true` but `fetched=false` (the clip exists in Frigate but the local cache has not caught up yet), the store schedules a single re-probe after 8 seconds so the UI reflects auto-caching completing without requiring any user interaction.

## [2.9.8] - 2026-04-15

### Added
- **UI:** Leaderboard species page gains a hero card at the top of the detail panel: shows the most recent detection thumbnail for the selected species, a live pulse indicator when a detection occurred in the last 60 minutes, and a colour-coded confidence badge (green/amber/red by threshold tier).
- **UI:** Species comparison chart is redesigned — the previous line chart is replaced with a donut breakdown (detection share by species) and a stacked bar timeline, giving a clearer at-a-glance picture of species proportions and activity patterns over the selected period.
- **Backend:** Model download integrity verification now reads `sha256`, `labels_sha256`, and `weights_sha256` fields from the downloaded `model_config.json` sidecar, in addition to any values in the Python registry. Config-file values take precedence, so model refreshes on the GitHub Release page are verified without requiring a code deploy. All shipped model config files on the release have been updated with verified checksums sourced from the live production container.

### Changed
- **UI:** Leaderboard weather overlay legend entries (Temperature, Wind Speed) are no longer shown as coloured label boxes — the Y-axis scale alone communicates the range. Both axes remain visible when overlays are active; only the redundant legend items are suppressed.
- **UI:** Sidebar active navigation item now has a 3px left-edge accent bar in the theme's primary colour (teal in default, blue in bluetit) so the current route is immediately legible at a glance instead of relying on the faint background tint alone.
- **UI:** Inactive sidebar navigation text is slightly brighter in dark mode (`slate-300` instead of `slate-400`) for better readability against the near-black background.
- **UI:** Bluetit theme sidebar now has a subtle blue-50 background tint so it feels cohesive with the rest of the blue theme rather than matching plain light mode.
- **UI:** Bluetit light-mode detection cards now have a stronger blue-tinted box-shadow and a more opaque border so cards are clearly distinct from the `#eef3fb` page background.

### Fixed
- **Fixed:** Leaderboard chart no longer compresses the plot area when weather overlays (temperature or wind) are active. The right-side weather axes now use `tickAmount: 4` and a capped label width so they occupy a predictable, compact column regardless of value range.
- **Fixed:** Featured "last N days" stat card on the leaderboard now uses an emerald-tinted background accent instead of a straight top border, which clashed visually with the card's rounded corners.
- **Fixed:** Heading hierarchy on Dashboard and Species pages corrected from h1→h3 jumps to h1→h2, fixing a WCAG sequential-heading-order violation flagged by Lighthouse.
- **Fixed:** Detection card overlay badges (favourite star, verified tick, audio-confirmed mic) now carry `role="img"` so screen readers do not encounter `aria-label` on an element with no accessible role.
- **Fixed:** "Last 3 days" pill text on the Dashboard discovery feed now uses `text-slate-600` instead of `text-slate-500`, bringing the contrast ratio from ~3.4:1 to ~4.7:1 and passing WCAG AA for small text.
- **Fixed:** Detection card image overlay badges now use a slightly more opaque backdrop (`bg-black/60`) so count and status labels remain legible over bright image backgrounds.
- **Fixed:** MQTT event task dictionaries (`_event_task_tails`, `_event_tail_depths`, `_event_pending_tasks`, `_event_pending_payloads`) now have orphaned entries swept out periodically. Followup tasks created inside `_run_pending` did not register done-callbacks, so if a task completed while no new MQTT activity arrived for that event the corresponding tail entries could accumulate indefinitely. The connection watchdog now calls `_sweep_stale_event_task_entries()` on each iteration to remove entries whose tasks are done and have no pending work.
- **Fixed:** SSE stream connections authenticated with a JWT token are now terminated gracefully when the token expires during a long-lived session. The event generator checks token expiry every 60 heartbeats (~20 minutes) and sends a `session_expired` event before closing the stream, instead of the previous behaviour of keeping stale sessions alive indefinitely.
- **Fixed:** Notification and service-test endpoints (`/settings/mqtt/test-publish`, `/settings/notifications/test`, `/settings/birdweather/test`, `/settings/llm/test`) now return proper HTTP status codes for error cases. External service failures (unreachable broker, failed webhook, bad token) return `502`; configuration/validation errors (missing token, disabled service, unknown platform) return `400`. Previously all error paths returned `200` with a `"status": "error"` body, which masked failures from any HTTP-aware caller.

## [2.9.7] - 2026-04-15

### Security
- **Fixed:** Rate-limit IP spoofing via `X-Forwarded-For` — the login brute-force protection now uses `request.client.host` (already normalised by `ProxyHeadersMiddleware`) instead of reading raw proxy headers directly. Previously, any client could set `X-Forwarded-For: 1.2.3.4` and bypass the 5-per-minute login limit entirely.
- **Fixed:** Git hash and branch name are no longer returned in the unauthenticated `/api/version` response, reducing reconnaissance surface. Both fields remain available in the authenticated `/api/health` endpoint.
- **Fixed:** JWT expiry `datetime` is now kept timezone-aware throughout token validation instead of stripping timezone info after decode, preventing potential naive/aware comparison bugs in downstream code.
- **Fixed:** Discord notification errors no longer risk logging the webhook URL — `httpx` exception strings could include the request URL; the error log now records only the exception type and response status.

### Fixed
- **Fixed:** Model downloads now include SHA-256 checksum verification infrastructure. When a `sha256`, `labels_sha256`, or `weights_sha256` field is present in the model registry entry, the downloaded file is verified before activation. Entries without checksums log a warning. This closes the path where a truncated or tampered download could be silently activated as the live ML model.
- **Fixed:** The three per-event lock dictionaries in the Frigate media proxy (`_preview_locks`, `_recording_clip_fetch_locks`, `_snapshot_generation_locks`) are now `WeakValueDictionary` instances. Entries are automatically removed once no coroutine holds a reference, preventing unbounded memory growth over long-running deployments with thousands of unique event IDs.
- **Fixed:** Partial video download temp files are now guaranteed to be cleaned up when an auto-video classification task is cancelled mid-download, preventing leaked `.mp4` files accumulating in the OS temp directory.
- **Fixed:** `location_temperature_unit` is no longer silently dropped when submitted alongside `location_weather_unit_system` in a settings save. Both fields are now applied independently.
- **Fixed:** Duplicate MQTT event inserts (same `frigate_event` ID, possible after service restart) are now treated as idempotent and logged at debug level instead of being recorded as pipeline stage failures.
- **Fixed:** `_table_columns()` in `DetectionRepository` now validates the table name against an explicit whitelist before executing the `PRAGMA table_info()` query. The same pattern is applied to the `GET /api/debug/db/stats` endpoint.
- **Fixed:** The taxonomy repair endpoint no longer uses a redundant `is_running` pre-check before acquiring the maintenance coordinator lock. The coordinator's `try_acquire()` is the authoritative serialiser and the pre-check was a TOCTOU race.
- **Fixed:** Taxonomy repair job progress bar now correctly shows `failed` (red) when the repair errors out. Previously `progress_state === 'failed'` fell through to `closeActiveByPrefix('stale')`, making a failed repair visually indistinguishable from a job that never ran.

## [2.9.6] - 2026-04-15

### Fixed
- **Fixed:** The MQTT stall watchdog no longer fires false-positive reconnects when the feeder is genuinely quiet. YA-WAMF now subscribes to the `frigate/available` retained MQTT topic (published by every Frigate instance since v0.9.0) and uses it as an availability gate: when Frigate explicitly reports `"online"`, all stall-reconnect paths are suppressed regardless of how long `frigate/events` has been silent. When `"offline"` is received, a focused `frigate_went_offline` diagnostic is recorded immediately instead of waiting 30 minutes. When the topic has never been seen, all existing stall-check behaviour is preserved unchanged as a fallback. The `/health` endpoint now exposes a `frigate_availability` dict with `status` and `last_seen_age_seconds`, and the `stall_recovery_warning_active` flag is suppressed while Frigate is confirmed online so the system no longer reports a degraded status during normal feeder quiet periods. (Issue #18 / #33 false-positive follow-up)
- **Fixed:** The taxonomy repair job progress bar now shows as completed instead of stale after the repair finishes. The Settings page was unconditionally calling `closeActiveByPrefix('taxonomy:', 'stale')` whenever `is_running` was false, which marked a just-finished job as stale on every subsequent poll. The handler now checks the backend-provided `progress_state` field and calls `markCompleted` when the job has finished, mirroring the pattern used by the batch analysis handler. (Issue #33)

## [2.9.5] - 2026-04-13

### Fixed
- Detection and events modals now force-probe full-visit clip availability when opened, clearing stale `unavailable` cache from a previous check.
- Detections list, settings, and auth feature flags now refresh automatically after tab regains focus or after SSE reconnects, catching events missed during connection gaps.

## [2.9.4] - 2026-04-13

- **Fixed:** The Errors page pipeline card no longer shows `CRITICAL` status for historical stage failures that have already resolved. The card now reflects `critical_failure_active` (which expires 300 seconds after the last failure) so the status clears automatically once the pipeline recovers, and the summary line distinguishes an active critical failure from a resolved historical one. The incident-synthesis path in the diagnostics store also now guards on the active flag, so a resolved historical failure no longer continues to produce new critical incident records on each health poll. (Issue #18 diagnostics follow-up)
- **Changed:** The MQTT Frigate-topic stall watchdog threshold (`MQTT_FRIGATE_TOPIC_STALE_SECONDS`) now defaults to 1800 seconds instead of 300. The previous 5-minute threshold caused the watchdog to fire continuously between bird visits on low-traffic feeders, producing repeated unnecessary reconnects and a small per-reconnect window where live Frigate events could be missed. The new default matches the real intent of the watchdog — detecting a genuinely stalled MQTT broker — while avoiding false-positive reconnects during normal feeder quiet periods. Note: the BirdNET-assisted stall check threshold (`MQTT_FRIGATE_TOPIC_STALE_SECONDS / 2`) moves to 900 s accordingly; on low-traffic feeders the independent 1800 s watchdog path becomes the primary stall detection path, which is the intended behavior. The env-var override remains available for operators who need a tighter threshold. (Issue #18)

## [2.9.3] - 2026-04-12

- **Fixed:** The owner-only timezone repair workflow now respects the same shared maintenance-work gate as backfill, taxonomy sync, and analyze-unknowns, so it cleanly returns a busy response instead of overlapping other maintenance jobs. The repair scan is also now bounded to legacy detections from the March 31, 2026 UTC timestamp regression window instead of sweeping the full detections table. (Issue #39 follow-up)
- **Changed:** Maintenance workflow concurrency is now controlled independently from video-analysis concurrency. A dedicated `maintenance_max_concurrent` setting defaults to `1`, so backfill, taxonomy repair, timezone repair, analyze-unknowns, and queued maintenance video work remain serialized by default even when owners raise `video_classification_max_concurrent` for clip analysis throughput. The Settings UI now explains that `1` is the recommended maintenance value and clarifies that in-process video analysis is safest at concurrency `1` unless the runtime has been explicitly validated under overlap. (Issue #33 / maintenance hardening)
- **Fixed:** Owner diagnostics bundles and workspace payloads now include taxonomy-repair status and shared maintenance-slot status, so taxonomy failures and maintenance-lane pressure are preserved in support artifacts instead of showing up only as unrelated health noise. (Issue #33 diagnostics follow-up)
- **Fixed:** Live MQTT classification now falls back more defensively when the primary Frigate cropped snapshot is temporarily unavailable. If the cropped snapshot path returns `404` or another fetch failure, YA-WAMF now retries within the normal freshness budget and then falls back through the uncropped Frigate snapshot, Frigate thumbnail, and any cached snapshot before dropping the event as `classify_snapshot_unavailable`. High-quality bird crop replacement now also prefers Frigate `box` / `region` hints before invoking the local crop detector, reducing unnecessary crop-model work when Frigate already provides a usable bird box. (Issue #18 / #33 follow-up)
- **Fixed:** YA-WAMF now includes an owner-only timezone repair workflow for legacy detections affected by the March 31, 2026 UTC timestamp normalization change. The backend can preview and apply safe repairs by validating each stored detection time against the corresponding Frigate event `start_time`, only rewriting rows whose difference is a whole-hour timezone offset. Ambiguous rows and detections whose Frigate events are no longer available are left untouched instead of being guessed. The Settings Data tab now exposes this repair flow with localized UI strings. (Issue #39)
- **Fixed:** CUDA inference capability detection now fails closed when ONNX Runtime advertises `CUDAExecutionProvider` but the provider cannot actually load inside the container. YA-WAMF now runs a safe CUDA provider probe before marking CUDA available, falls back cleanly to CPU when NVIDIA runtime libraries are missing (for example `libcublasLt.so.12`), and surfaces the probe failure in Detection settings instead of repeatedly attempting a broken CUDA path. (Issue #18 follow-up)
- **Fixed:** The official backend and monolithic images now package the CUDA 12 / cuDNN 9 userspace runtime needed by `onnxruntime-gpu`, and YA-WAMF explicitly preloads those packaged libraries before probing or creating CUDA sessions. With a normal NVIDIA container runtime on the host (`gpus: all` / NVIDIA Container Toolkit), CUDA inference should now work as a supported image path instead of depending on ad-hoc host library injection. (Issue #18 follow-up)
- **Fixed:** Live event processing now treats Frigate snapshot unavailability as a bounded recovery condition when MQTT status shows a Frigate stall or stall-recovery reconnect in progress. Instead of dropping immediately after one 2-second retry, the event processor now keeps retrying snapshot fetches for a short, freshness-bounded window so brief Frigate outages or reconnect gaps do not turn into `classify_snapshot_unavailable` drops while BirdNET and MQTT recovery are still healthy. (Issue #33 follow-up)
- **Fixed:** Issue `#33` background maintenance work is no longer allowed to starve indefinitely behind a continuously busy live pipeline. The classifier admission coordinator now grants aged background image work a bounded starvation-relief slot after a short wait, and the maintenance video queue similarly allows one aged maintenance start through under live pressure unless MQTT pressure is already critical. Status payloads now expose when starvation relief is active so diagnostics can distinguish genuine hangs from intentional prioritization. (Issue #33 follow-up)
- **Fixed:** Issue `#33` owner-triggered maintenance now exposes explicit queue-health state and applies safer admission guardrails. Maintenance video status now reports when work is merely queued, deprioritized behind live traffic, stalled under sustained pressure, or recovering from repeated failures. Repeated `Analyze Unknowns` requests now coalesce into the current in-progress batch instead of piling on more maintenance work, while taxonomy repair and historical backfill reject new starts when maintenance is already badly backlogged or a taxonomy run is active. (Issue #33 follow-up)
- **Fixed:** Top-level `/health` status now treats high MQTT handler concurrency as a pressure signal instead of an automatic degradation. YA-WAMF still reports MQTT `pressure_level`, but the service only flips to degraded for MQTT when handler-slot backlog waiting is actively blocking the message loop or a recent slot-wait exhaustion indicates real saturation. This keeps the extreme `issue33-live` hammer profile from looking unhealthy solely because the broker is busy while events are still completing normally. (Issue #33 follow-up)
- **Fixed:** MQTT status now exposes backlog composition so `#33` live-hammer saturation is diagnosable instead of opaque. `/health` now reports per-topic in-flight counts, dispatch totals, Frigate event-tail depth, and whether BirdNET audio work is being coalesced. Under sustained BirdNET bursts, YA-WAMF now keeps only the freshest pending audio payload while one audio task is already active, instead of queuing every intermediate BirdNET MQTT message as separate in-flight work. This preserves recent-audio freshness while reducing low-value MQTT backlog growth under extreme combined load. (Issue #33 follow-up)
- **Fixed:** Issue `#33` Frigate-event backlog is now bounded per event instead of growing an arbitrarily deep same-event tail under extreme load. When newer actionable MQTT payloads arrive for an event that already has active work in flight, YA-WAMF now keeps only the freshest pending Frigate payload for that event, discards superseded intermediate updates, and exposes the superseded count in MQTT health. This preserves latest event state while reducing low-value duplicate work during heavy burst conditions. (Issue #33 follow-up)
- **Fixed:** Leaderboard species rows now use canonical species names for navigation instead of leaking arbitrary variant display labels from individual detections. That means Top Performers / Full Rankings entries such as `House Finch` or `Northern Cardinal` no longer open species modals using variant labels like `House Finch (Female/immature)` that could return `Not Found`. Leaderboard AI chart analysis now also includes weather and sunrise/sunset metadata from the rendered timeline when available, so weather-correlation summaries no longer claim the chart lacks weather data when the underlying leaderboard range already has it. (Issue #40)
- **Fixed:** The frontend no longer misreports backend startup/restart failures as an authentication prompt. When `/api/auth/status` is temporarily unavailable during startup, model reloads, or crash recovery, YA-WAMF now shows a backend-unavailable/retry state instead of collapsing into the login screen. This makes issue `#36` diagnosable as service instability rather than a false auth lockout.
- **Fixed:** Split-backend Docker installs now keep downloaded models on the persistent `/data` volume instead of the container filesystem. The backend image default now points at `/data/models`, and startup will migrate non-conflicting legacy `/app/data/models` entries forward when that older baked-in default is detected, without overwriting anything already present in `/data/models`. This prevents upgrades from continuing to use stale in-container model state that disappears on backend container replacement. (Issue #36 follow-up)
- **Fixed:** The blocked-species picker now searches cached taxonomy and stored detections in addition to the active classifier label list. That means nuisance non-bird taxa such as `Zebra Mussel`, `Bank Vole`, or other previously detected wildlife can be added to the structured blocked list even when the current model no longer exposes them directly. (Issue #37 follow-up)
- **Fixed:** Runtime classifier fallback now fails safely instead of silently installing an unloaded fallback model. When OpenVINO load falls back to ONNX Runtime CPU, or ONNX Runtime falls back to OpenVINO CPU, YA-WAMF now only adopts that fallback if the replacement model actually loads. Otherwise it continues to the final TFLite fallback instead of leaving the classifier in a broken `loaded=false` state that later produced empty historical-classification results. Historical backfill now also reports `background_image_model_unavailable` instead of the misleading generic `classification_failed` when the bird model is unavailable. (Issue #33 follow-up)
- **Fixed:** Model downloads no longer fail with a cross-device rename error (`EXDEV`) when the persistent data volume is mounted on a different filesystem than the container's writable layer. `model_manager` now falls back to a copy-then-delete strategy when `os.rename` raises `EXDEV`, and the `MODELS_DIR` resolution correctly detects a mounted `/data` volume even when the `models/` subdirectory does not yet exist. Bundled model files have been removed from the Docker image entirely — all models are downloaded from GitHub Releases at runtime. (Issue #38)
- **Fixed:** Blocked video classification results are now persisted and surfaced to the user. When a video analysis result matches a blocked species the result is stored in the database (`video_result_blocked` column) but not promoted to the primary detection species. The detection modal shows an amber "Matched a blocked species — not applied" note beneath the video label so owners can see why a video result was suppressed without having to infer it from missing data. (Issue #37 suggestion 1)
- **Fixed:** The video analysis section of the detection modal now displays the resolved common name instead of the raw scientific name when a wildlife-wide model (ConvNeXt, EVA-02) stores a scientific name as the video classification label but the primary detection already has a common name resolved. (Issue #37 suggestion 1)
- **Added:** Events multi-select now includes "Reclassify Selected" and "Delete Selected" actions alongside the existing "Manual Tag Selected" action. Bulk delete calls the new `POST /api/events/bulk/delete` endpoint which removes each detection, broadcasts an SSE `detection_deleted` event per item, and returns a summary with success and failure counts. (Issue #37 suggestion 2)
- **Added:** OpenRouter.ai is now a supported AI provider alongside Gemini, OpenAI, and Claude. Configure it by selecting "openrouter" in AI settings and entering an OpenRouter API key. OpenRouter's OpenAI-compatible API is used for both vision analysis and chat, allowing access to any model available on the OpenRouter platform. (Issue #37 suggestion 3)
- **Fixed:** The Events explorer now refreshes its species and camera filter options immediately after hide/delete mutations, including deletes triggered from the detection modal. Species with no remaining detections no longer linger in the Events species list until a manual refresh or page reload. (Issue #37 follow-up)

- **Changed:** The Jobs page now keeps `Recent` history stable and easier to scan, with newest-finished jobs first and compact job-type icons. The `Active` section now reflects the real backend model instead of inventing fake thread slots: it renders actual running jobs only, keeps their order stable by start time, and treats detection/weather backfills as coordinator jobs that manage classifier worker capacity rather than pretending one backfill job is multiple parallel job cards.
- **Fixed:** Detection AI naturalist results now persist cleanly in the UI after generation. The analysis endpoint returns the saved timestamp, the detection modal writes the fresh `ai_analysis` and `ai_analysis_timestamp` back into the current detection/store state immediately, and selected-detection sync now treats AI fields as first-class state so reopening a detection no longer drops a previously generated analysis. Manual retagging also clears stale AI analysis fields in the UI at the same time it invalidates the old species analysis.
- **Fixed:** Detection AI analysis now follows the same canonical media order as the rest of the app. Owner-triggered analysis now prefers a persisted full-visit recording clip when one exists, otherwise falls back to the Frigate event clip, and finally to a snapshot. Frame sampling stays middle-biased for both clip sources, with a wider central window for full visits so long visits are analyzed more gracefully.
- **Fixed:** The Jobs page now reconciles detection and weather backfill progress independently of the Settings page, so stale synthetic backfill lanes no longer linger in `Notifications & Jobs` after a job finishes or disappears from `/api/backfill/status`. Backfill lane polling also tolerates one failed kind-specific status fetch without freezing the other lane.
- **Fixed:** Low-priority image classification now uses longer admission windows for heavy background callers instead of immediately failing with `background_image_overloaded` after the default `0.5s` queue budget. Historical backfill snapshot classification and maintenance snapshot-fallback classification now pass a larger queue timeout into the background classifier, reducing false terminal capacity errors while leaving live-image responsiveness unchanged.
- **Changed:** The Jobs page now keeps active work in stable visual lane slots instead of reshuffling cards on every poll, and backfill/weather-backfill progress now derives a scoped total from observed progress when the backend reports a running job with `total=0`. The active slots also use clearer icon-led lane and idle states for faster scanning.
- **Fixed:** Detections are no longer reported as “missing in Frigate” when YA-WAMF still has cached media. The Events API now reports cache-backed snapshots and manually fetched full-visit clips honestly even after Frigate event metadata ages out, and the detection modal now uses a softer icon-only Frigate state instead of a hard red badge when media is still recoverable.
- **Fixed:** Maintenance video-classification timeouts for issue `#33` now degrade more safely. When an owner-triggered maintenance job times out and snapshot fallback is allowed, YA-WAMF now records richer timeout diagnostics (source, frame budget, clip probe data, provider/runtime context) and retries that item through snapshot classification instead of immediately treating the timeout as an unrecoverable failure. The video-classifier health payload now also exposes per-source timeout counters plus the latest live and maintenance timeout context.
- **Fixed:** Video-classification jobs are now source-aware for `#33` hardening. Owner-triggered maintenance/bulk analysis uses a separate maintenance breaker, so repeated batch `video_timeout` failures no longer open the live auto-video circuit that guards normal detections. Timeout diagnostics now also record the job source, camera, clip byte size, and runtime/provider context for easier root-cause analysis in exported bundles.
- **Changed:** Desktop navigation is now sidebar-only. The old horizontal desktop nav/layout mode has been removed, legacy stored `layout=horizontal` preferences are migrated back to `vertical`, the appearance layout picker is gone, and the current mobile menu/top-bar behavior stays unchanged.
- **Fixed:** Replacing a cached canonical snapshot now also invalidates the derived card thumbnail, so Events/Explorer cards cannot keep serving a stale pre-HQ image after snapshot regeneration or high-quality replacement.
- **Fixed:** Cleaned dead imports and an unused local from active backend runtime modules so `ruff` output is higher-signal again on the current media/species/auth work.
- **Fixed:** Detection-card thumbnail requests now prefer a derived thumbnail from the canonical cached snapshot when one exists, so Events/Explorer cards visibly benefit from HQ snapshot generation instead of continuing to show Frigate's tiny low-resolution thumbnails.
- **Fixed:** Backfilled detections now participate in the same high-quality snapshot pipeline as live ingest. YA-WAMF caches the backfill snapshot, queues HQ replacement without silently dropping overflow during large backfills, and when the original Frigate event clip is gone it now falls back to the best available full-visit recording clip instead of leaving the raw snapshot in place.
- **Changed:** Completed a broad UI translation pass across all supported locales (`de`, `es`, `fr`, `it`, `ja`, `pt`, `ru`, `zh`) for previously fallback-heavy active strings. Public-view badges, explorer controls, full-visit/video labels, diagnostics copy, leaderboard analytics controls, and new settings/debug/full-visit capability copy now resolve through locale files instead of inline English defaults.
- **Added:** Blue Tit color theme — a selectable accent palette inspired by the app icon that remaps teal/emerald accents to cobalt blue and golden yellow across cards, buttons, gradients, navigation, and focus rings. Selectable in Appearance settings alongside the existing font and layout options, with full i18n support.
- **Changed:** Detection cards redesigned for clarity. Image overlay reduced to confidence badge, time/play controls, and icon-only favorite/verified/audio badges. Audio details, weather breakdown, classification source, and Frigate score moved to the detection modal only. Weather now shown as a compact condition icon with temperature. Camera and date collapsed to a single metadata line.
- **Changed:** Dashboard hero card streamlined to show time, camera, weather condition, and temperature in a single compact row with SVG icons instead of emoji. Detailed weather pills (rain, snow, cloud cover, wind speed) removed from the hero overlay — full weather breakdown remains accessible in the detection modal. Discovery Feed section divider now uses a bottom border, bolder typography, and bordered badge for clearer visual separation from the hero area.
- **Added:** Frigate object-detection score now displayed in the detection modal metadata grid so it remains accessible after removal from the card overlay.
- **Changed:** Leaderboard page redesigned for clarity and visual polish. Removed duplicate hero stat pills, added accent borders and color-coding to summary cards (emerald/amber/sky), consolidated chart controls into a single toolbar row, collapsed weather overlays into an expandable section with active-state toggle styling, replaced chart stat badges with a compact inline summary, redesigned top-3 podium cards with gradient rank badges and proportional detection count bars, upgraded species table with larger rounded thumbnails, inline count bars, striped rows, and color-coded trend values, and added section wayfinding labels.
- **Fixed:** MQTT stall-recovery reconnects are now capped at a configurable maximum (default 5) consecutive no-Frigate reconnects. When the cap is reached, YA-WAMF stops the reconnect loop and records a focused `frigate_recovery_abandoned` diagnostic directing the user to check their Frigate MQTT topic configuration, instead of reconnecting endlessly when Frigate is permanently unreachable or misconfigured (Issue #33 hardening).
- **Fixed:** Video classifier temporary file cleanup now suppresses `OSError` so a secondary cleanup failure cannot mask the actual classification result or error.
- **Fixed:** eBird CSV export now annotates the species comment and submission comment columns with `common name unavailable` when a row falls back to the scientific name because no English common name could be resolved. This makes scientific-name-only rows visually identifiable before eBird import (Issue #23 hardening).
- **Added:** Deploy-recovery now tracks a cumulative recovery-attempt counter in local storage (`getRecoveryCount()`). Diagnostics bundles can inspect this to determine whether a user's tab has been stuck in a repeated reload loop versus a one-time recovery event (Issue #35 hardening).
- **Added:** Regression coverage for circuit-breaker auto-close after cooldown expiry, MQTT stall-recovery reconnect cap and abandoned-diagnostic recording, `MqttError`-path intentional-reconnect flag clearing, and Home Assistant coordinator resilience to malformed `latest_detection` payloads (missing `frigate_event`, non-string `detection_time`, non-integer `total_count`).
- **Fixed:** Automatic video-analysis state now truly takes over detection cards. While a card is being analyzed, the analysis overlay sits above all other card chrome, the timestamp/play/full-visit/action controls are suppressed, and the card border shifts to an analysis accent so hidden controls no longer bleed through above the progress UI.
- **Fixed:** Thumbnail and full snapshot cache behavior are now separated. `thumbnail.jpg` no longer poisons the canonical event snapshot cache, the detection details modal now uses `snapshot.jpg` instead of the low-resolution thumbnail route, and the full snapshot proxy self-heals obviously thumbnail-sized cached "snapshots" by evicting and refetching them.
- **Fixed:** Manual tagging in the Events explorer is now consistently owner-only. The UI no longer exposes multi-select tagging or modal retag/reclassify/delete controls until auth status has loaded successfully and owner access is confirmed, and auth-status load failures now fail closed instead of leaking owner controls.
- **Changed:** The Events explorer multi-select cards now use a full selected-card veil instead of the old in-image `Select` / `Selected` pill or a weak corner selector. Selected cards now get a bolder cyan card border, a frosted cyan-blue overlay above the card content, and a centered checkmark so bulk selection reads clearly from the grid while intentionally masking the underlying card details.
- **Changed:** Full-visit playback now uses a single canonical clip contract in the UI. The player always opens `/api/frigate/{event_id}/clip.mp4`, promoted full visits replace the canonical clip automatically for both authenticated and guest/public viewers, and the old event-vs-full toggle has been removed in favor of a passive full-visit indicator.
- **Fixed:** MQTT stall recovery now stays armed across reconnect boundaries for the `#33` live-ingest failure mode. If a Frigate-topic stall triggers a reconnect and BirdNET remains active in the next MQTT session, YA-WAMF can now detect that Frigate still never resumed and force another recovery reconnect instead of going blind because the new session had zero Frigate messages.
- **Added:** MQTT health now raises a focused stall-recovery warning when Frigate still has not resumed after a prior BirdNET-assisted recovery reconnect. `/health` now exposes the consecutive no-Frigate reconnect count and degrades status while that post-reconnect blind spot is still active, making issue `#33`-style live-ingest regressions visible before users have to infer them from missing detections.
- **Added:** A dedicated `scripts/run_issue33_harness.py` soak harness now exercises the live-ingest and batch-video symptoms seen in issue `#33`. It can stop synthetic Frigate traffic while BirdNET keeps flowing, optionally add unknown-analysis pressure, and fails on missing MQTT recovery reconnects, video-circuit openings, or excessive video-queue backlog.
- **Fixed:** The issue `#33` harness now treats its own induced Frigate stall as test stimulus rather than an automatic failure. A run now passes when BirdNET stays active, the required MQTT liveness reconnect occurs, and the video queue stays healthy, instead of inheriting issue-22 semantics that always fail on the intentionally created stall window.
- **Changed:** The issue `#33` harness can now log in with owner username/password directly instead of requiring a manually copied JWT. Credential-based runs fail with clearer login errors, and the run summary records whether authenticated owner pressure was exercised without writing the password into artifacts.
- **Fixed:** Auto-generated full-visit clips no longer cache prematurely truncated recording windows. YA-WAMF now waits until the requested Frigate recording span should be complete before fetching, validates cached `_recording.mp4` clips against the expected window duration, and evicts stale short recording clips plus their preview assets so later requests can self-heal from Frigate instead of serving a permanently shortened “full visit”.
- **Fixed:** The Home Assistant integration no longer treats `Last Bird Detected` as a plain species-name-only state for repeated detections. The sensor now only emits when a new detection event arrives, so repeat visits from the same species do not get silently swallowed by unchanged coordinator polls.
- **Added:** Home Assistant now exposes `Last Detection Event` and `Last Detection Time` sensors. These provide stable automation triggers for every new detection and a proper timestamp entity instead of relying on raw string attributes.
- **Fixed:** `/api/stats/daily-summary` now computes its 24-hour window using the same naive-UTC basis as persisted detections. This prevents Home Assistant and other clients from lagging behind recent detections when the host local timezone is offset from UTC.
- **Fixed:** Rolling-summary follow-on contracts are now aligned with that UTC window. The Home Assistant count sensor now models the API value as a rolling 24-hour measurement instead of a monotonic "today" total, daily-summary species cards now choose their representative `latest_event` by newest `detection_time` instead of lexicographic event id, and nearby AI/video-share timestamp responses now use the same explicit-UTC serialization contract as the main detection API.
- **Fixed:** The Home Assistant polling coordinator now normalizes malformed `latest_detection`, `top_species`, and `total_count` fields from `/api/stats/daily-summary` instead of leaking invalid payload shapes into sensor state.
- **Added:** Owner diagnostics workspace exports now preserve raw backend diagnostic events and a focused `video_classifier` summary in downloaded issue bundles. Circuit-breaker incidents now carry the latest `video_circuit_opened` context, likely last error, and recent video-classifier events so support bundles retain the root-cause evidence instead of only the grouped health symptom.
- **Changed:** The `Error Bundles` section on the owner `Errors` page now highlights the newest captured bundle in a dedicated availability card and presents saved bundles as clearer cards with a pinned `Newest` state, notes preview, and stronger empty-state copy.

- **Changed:** Browser E2E smoke tests now accept `YAWAMF_BASE_URL` for monolith runs instead of assuming the legacy split-stack `yawamf-frontend` hostname, and the leaderboard inspection smoke test now expects the raw histogram default instead of the old area-chart default.
- **Fixed:** MQTT stall-recovery reconnects no longer get stuck in a clean reconnect loop. When the watchdog intentionally disconnects a stalled MQTT session, the client now clears its pending reconnect flag on the normal post-loop path as well as the `MqttError` path, preventing the monolith from reconnecting endlessly without ever consuming new Frigate or BirdNET messages. This restores recent-audio freshness and normal MQTT topic counters after a stall-recovery event.
- **Changed:** The leaderboard page now opens the `Detections over time` chart in raw histogram mode by default, with smoothing disabled until the user opts in through the existing chart controls.
- **Fixed:** Stale tabs now recover more cleanly after deploys. The app shell classifies chunk-load and dynamic-import failures as likely stale-bundle errors, performs a guarded one-shot reload per frontend build, and falls back to a warning toast instead of looping if the same stale-bundle condition persists after reload.
- **Fixed:** Owner health checks now treat a backend/frontend build mismatch as a deploy-recovery signal instead of only a diagnostics signal. When the backend version moves ahead of the current bundle, the app uses the same guarded reload path to refresh an old tab before its stale UI state drifts further.
- **Added:** Pure deploy-recovery regression coverage now locks in the stale-bundle classifier, one-shot reload guard, warning fallback, and backend/frontend version-drift handling.
- **Fixed:** Batch-analysis progress cards now recover cleanly after a backend redeploy or restart. When owner health checks detect a new backend `startup_instance_id`, the frontend clears only the synthetic `reclassify:progress` batch state and lets the next successful queue-status poll recreate it if work is still running, preventing old tabs from showing a stale `Working...` batch card indefinitely after `/api/maintenance/analysis/status` returned transient `502` errors during a deploy.
- **Fixed:** Owner queue-status polling now explicitly bypasses browser/proxy caches and also self-heals orphaned synthetic `Batch Analysis` jobs. If a tab misses the terminal batch update but later receives a fresh zero-queue `/api/maintenance/analysis/status` response, the stale `reclassify:progress` card is settled automatically instead of lingering at states like `0 / 21 · 1 stale` until a manual refresh.
- **Added:** Live-update regression coverage now asserts that backend instance changes clear orphaned synthetic batch-analysis state without removing per-event reclassify jobs or per-event progress notifications.
- **Fixed:** Detection and stats timestamps now follow an explicit UTC API contract instead of leaking naive server-local datetimes. New detections, notification/update timestamps, SSE payloads, daily summary latest-detection cards, leaderboard species `first_seen` / `last_seen`, species stats, and related nested detection responses now serialize datetimes with an explicit `Z` suffix so browsers render the correct local wall time instead of treating UTC values as already-local timestamps.
- **Added:** Regression coverage now asserts explicit UTC serialization on live detection broadcasts, `/api/events` rows, `/api/stats/daily-summary` latest detections, and species stats `first_seen` / `last_seen` / `recent_sightings` payloads, including legacy naive timestamps already stored in SQLite.
- **Fixed:** The species leaderboard no longer throws `500 Internal Server Error` when `Unknown Bird` rows are present. The canonical unknown-species leaderboard window query now binds the correct rolling-window parameters for the aggregate camera-count and outer `WHERE` clauses, fixing the live SQL binding error on `/api/leaderboard/species`.
- **Fixed:** Timeline compare-series queries on the leaderboard page now include the canonical taxonomy join they rely on when resolving selected species names. This fixes the live `no such column: tc_filter.taxa_id` failure on `/api/stats/detections/timeline` when the page requests compare lines for real species.
- **Added:** Leaderboard regression coverage now exercises both `/api/leaderboard/species` with hidden noncanonical detections and `/api/stats/detections/timeline` with canonical compare-species selections, so the page’s top-species and detections-over-time sections cannot silently regress independently.

- **Changed:** YA-WAMF now documents the coming deployment transition more explicitly. `v2.x` continues to support the legacy split frontend/backend stack, but `v3.0` is now planned around a monolithic single-container deployment with a dedicated split-to-monolith migration path in the docs.
- **Fixed:** Species-name normalization for Issue #26 is now hardened across all major backend surfaces instead of only the Explorer lists. Broad and non-species model labels such as `Life (life)` and `... and allies` are now treated as `Unknown Bird` consistently for live snapshot saves, video reclassification promotion, SSE/live-update payloads, species search/catalogue pages, daily summary cards, timeline compare overlays, and maintenance unknown-detection selection.
- **Added:** A shared canonical-species helper now centralizes hidden-label handling and user-facing masking for `display_name`, `category_name`, and taxonomy fields. This preserves raw classifier labels in storage for diagnostics while ensuring normal UI/API responses only expose canonical species or `Unknown Bird`.
- **Changed:** `Unknown Bird` matching is now repository-backed and canonical. Query/filter paths no longer depend solely on exact configured unknown labels; they also include hidden noncanonical labels across `display_name`, `category_name`, `scientific_name`, and `common_name`, which keeps filtering, stats, and maintenance jobs aligned with the new masking rules.
- **Fixed:** Blocking `Unknown Bird` now also blocks hidden noncanonical model outputs that would be surfaced as `Unknown Bird` to users, preventing a policy gap where broad labels bypassed the owner’s blocklist.
- **Fixed:** Auto/video classification can no longer reintroduce hidden noncanonical labels as the primary stored species. Video results now refuse to downgrade a known species to a broad/noncanonical label and only promote such labels back to `Unknown Bird` when the existing detection is already unknown.
- **Fixed:** Species and stats aggregates for `Unknown Bird` now include historical hidden noncanonical labels, so leaderboard totals, species-detail counts, recent sightings, daily summary latest-detection cards, and timeline compare series all remain internally consistent after the canonical masking change.

- **Added:** Canonical species identity normalization is now completed end to end. YA-WAMF now treats species identity as `taxa_id` first, then `scientific_name`, instead of relying on raw `display_name` equality for key repository filters and historical rollups.
- **Added:** The maintenance taxonomy-repair action now runs an explicit canonical-identity repair flow that backfills missing taxonomy on historical detections and rebuilds species rollups afterward, so repaired rows immediately collapse into the correct canonical species stats.
- **Changed:** `species_daily_rollup` now stores canonical identity fields (`canonical_key`, `scientific_name`, `common_name`, `taxa_id`) and is rebuilt on canonical keys instead of display name alone, which prevents common/scientific alias variants from splitting leaderboard windows and recent metrics.
- **Fixed:** Canonical taxonomy lookups can now resolve localized common names even when no language hint is available, which hardens maintenance repair and other backend-only reconciliation paths against historical localized labels.
- **Fixed:** Canonical identity repair now uses a safer maintenance policy: it backfills missing canonical taxonomy fields and rebuilds canonical rollups without rewriting already-populated localized `common_name` values just because they are non-ASCII.
- **Fixed:** Species-rollup rebuilds now use an atomic staging-table swap instead of deleting the live rollup table first. A failed maintenance repair can no longer leave `species_daily_rollup` empty, and the normal incremental rollup path retains its original idempotent `ON CONFLICT` upsert behavior.
- **Fixed:** Species detail endpoints no longer double-count canonical species aliases after the repository helpers were normalized. Species stats now query canonical species once per request, while the explicit multi-label aggregation path remains reserved for `Unknown Bird` handling.
- **Fixed:** Canonical identity repair no longer treats a localized stored `common_name` as damaged just because it is non-ASCII. Repairs remain additive for `common_name`, which preserves localized rows such as Cyrillic species names while still backfilling missing canonical taxonomy fields and serving localized read paths through `taxonomy_translations`.
- **Changed:** Manual video reclassification now prefers the persisted full-visit recording clip when one is already cached for the same Frigate event, instead of falling back to the shorter event clip or re-downloading unnecessary media.
- **Changed:** Video frame sampling is now clip-aware. Normal Frigate event clips bias their sampled frames toward the center while still covering the edges, and persisted full-visit clips use a broader whole-visit sampling pattern with lighter center emphasis.
- **Fixed:** The video player now treats already-persisted full-visit clips as the canonical `/clip.mp4` path instead of trying to reload them through the separate recording route, which fixes stale short-clip labeling and the stuck `Loading...` state when toggling to `Full visit` for previously fetched events. The mobile video-action row now wraps cleanly instead of overflowing its buttons.
- **Changed:** Delayed notifications now derive their effective video wait from the actual video-classification pipeline timing, including the clip polling backoff budget, so `delay_until_video` cannot silently time out before video analysis has a real chance to complete. The existing notification timeout now acts only as a larger manual override instead of a smaller cutoff.
- **Fixed:** Manual tag updates now preserve full-visit readiness for the same Frigate event. When a persisted full-visit clip already exists, renaming a detection refreshes that event-based clip state instead of re-offering a redundant `Fetch full clip` action.
- **Changed:** HQ Event Snapshots section in Settings > Data has been reworked for clarity. The toggle is now a dedicated card with a persistent amber **Beta** label, a description line always visible, and an animated sub-panel for the bird-crop and JPEG quality options that only appears when HQ snapshots are enabled. The basic snapshot and video clip cache toggles remain as a compact 2-column grid above it.
- **Changed:** Blue Tit is now the default colour theme for new installs. Existing installs keep their stored preference; this only affects first-run or cleared-storage scenarios. The backend `config.json` default has also been updated to match.
- **Fixed:** The default (teal) colour theme swatch in Appearance settings now renders as a solid teal block instead of a gradient. Only the Blue Tit swatch uses a gradient; each theme now has its own correctly styled swatch.
- **Changed:** Documentation updated for monolith-first deployment. All user-facing docs now lead with `yawamf-monalithic` examples, container command references updated from `yawamf-backend` to `yawamf-monalithic`, Swagger/OpenAPI access clarified (not proxied through monolith nginx), `canary` framing removed, and `:dev` tag in stable-use examples replaced with `:latest`.
- **Changed:** Legacy split deployment (`wamf-frontend` + `wamf-backend`) now carries an explicit end-of-updates notice: no bug fixes, new features, or compatibility guarantees will be provided for the split stack starting with v3.0. Documented in README and the split-to-monolith migration guide.

## [2.9.1] - 2026-03-27

- **Added:** When recording clips and the media cache are enabled, YA-WAMF now auto-generates a persisted full-visit clip for eligible completed detections after the Frigate `end` event instead of requiring manual fetch for each event.
- **Added:** A bounded background reconciler now revisits recent detections that are old enough to have a complete full-visit window and backfills any missing persisted full-visit clips when the original MQTT `end` event was missed or recordings were briefly unavailable.
- **Changed:** YA-WAMF's canonical `/api/frigate/{event_id}/clip.mp4` route now prefers the persisted `{event_id}_recording.mp4` full-visit file when one exists, so the longer clip transparently replaces the short Frigate event clip inside YA-WAMF without modifying Frigate itself.
- **Changed:** The full-visit ready indicator now uses a compact icon-only treatment beside the play button with hover text, and the video player collapses the old short-vs-full toggle once the persisted full-visit clip has replaced the canonical event clip.
- **Changed:** Locale coverage has been expanded again across active settings and jobs surfaces, and a new locale audit test now guards against untranslated English carryover in the highest-traffic non-English UI paths.

## [2.9.0] - 2026-03-26

- **Added:** YA-WAMF can now serve a first-class `Full visit` clip variant from Frigate continuous recordings. Owners can enable it in Settings → Connection → Frigate, choose how many seconds before/after the detection to include, and switch between the original event clip and the longer recording window in the VideoPlayer without leaving the modal.
- **Added:** The Frigate settings panel now includes a recording-clip capability check that inspects the saved Frigate config, reports whether continuous recordings appear usable for the selected cameras, and shows the detected retention window before allowing the feature to be turned on.
- **Added:** Full-visit clips now work through the same access paths as normal event clips, including share links and public-access playback, using the new `/api/frigate/{event_id}/recording-clip.mp4` proxy route and a distinct media-cache key of `{event_id}_recording.mp4`.
- **Added:** Detection Settings now uses a species-search picker for blocked species. New selections are stored as structured `blocked_species` entries with taxonomy identifiers, while unresolved legacy `blocked_labels` continue to render as removable `Legacy` chips for backward compatibility.
- **Added:** A small manual-tag search policy helper now centralizes when the picker should request taxonomy hydration for typed queries, making the modal behavior explicit and regression-testable.
- **Fixed:** The blocklist now matches against both legacy raw labels and structured blocked-species entries across live detection filtering, post-taxonomy save paths, auto video classification writes, and manual reclassification. Blocking a species via the picker now reliably catches common-name, scientific-name, and `taxa_id` matches instead of depending on a fragile exact raw-label string.
- **Fixed:** The manual tag / reclassify picker now hydrates missing taxonomy data for meaningful typed searches instead of only during the initial empty-query load. Species that have never previously been detected can now show a clean common-name primary label and scientific-name subtitle while searching.
- **Fixed:** Species search hydration now strips trailing classifier parentheticals before taxonomy lookup, so labels like `"Cassin's Finch (Adult Male)"` resolve through `"Cassin's Finch"` instead of failing iNaturalist/common-name hydration.
- **Fixed:** Full-visit fetching is now available from the detection details modal as well as the event card. When a recording span is available, owners can fetch the full clip directly from the modal, and detections that have already fetched it show a `Full visit` badge in the media header.
- **Fixed:** Fetched full-visit clips now persist correctly across modal reopen and page reload instead of falling back to the short default clip. The recording-clip probe now reports when a cached full visit already exists, the frontend remembers fetched full visits per event, and the `Fetch full clip` action has been moved out of the snapshot center overlay to sit below the detection timestamp.
- **Fixed:** Detection source badges and confidence panels now reflect the current visible classification source instead of blindly mirroring the historical `manual_tagged` feedback flag. Manual tags that were later superseded by a completed video result no longer leave stale `Manual` pills behind on cards, the hero, or the details modal.
- **Fixed:** Full-visit availability probes now handle streamed Frigate `404` responses safely and use the current camera-recording route shape that Frigate actually exposes. This prevents the fetch button from being hidden behind a probe-side `500` and restores full-visit availability detection for live installs using Frigate's `/api/{camera}/start/{start_ts}/end/{end_ts}/clip.mp4` endpoint.
- **Fixed:** Authentication setup and settings now enforce the same password policy client-side as the backend and surface readable validation failures instead of `[object Object]` or a generic `Failed to save settings` banner. FastAPI/Pydantic validation payloads are normalized into user-facing messages, so username/password setup errors now explain the real problem.
- **Changed:** Locale coverage has been expanded again across the highest-traffic owner flows. Full-visit video controls, detection AI conversation copy, Frigate connection state, shared error-boundary text, and the entire `Settings → Data` section now have localized strings in all supported UI languages instead of falling back to English.
- **Changed:** `ROADMAP.md` and `ISSUES.md` were refreshed to match the current GitHub tracker state: issue `#16` and issue `#21` are closed, the issue-first section no longer points at stale open work, and roadmap item 7 is marked complete on `dev`.
- **Changed:** Roadmap item 1, `Blocked Species — Species Picker + Reliable Matching`, is now completed on `dev`.
- **Changed:** Roadmap item 0, `Full-Visit Recording Clip ("Bird Lifecycle View")`, is now completed on `dev`.

## [2.8.7] - 2026-03-26

- **Fixed:** Blocked labels did not suppress detections where the model outputs a parenthetical plumage or age suffix — for example, `medium_birds` produces `"Cassin's Finch (Adult Male)"` and `"Cassin's Finch (Female/immature)"`, neither of which matched a blocklist entry of `"Cassin's Finch"`. The blocked-label check in the real-time detection pipeline, the post-taxonomy enrichment check, and the manual-tag guard now all strip trailing parentheticals before comparing against the blocklist. The auto video classifier path, which previously had no blocked-label check at all, now also applies the same logic — and always writes the video classification result to the database before returning so that the stale-video watchdog cannot cause an infinite re-queue loop for blocked species (Issue #31).
- **Fixed:** Classifier health remained `degraded` after downloading the active model via the Model Manager. Downloading a model never triggered a classifier reload; only clicking Activate did. The model manager now automatically calls `reload_bird_model()` after a successful download if the downloaded model matches the currently active selection, recovering health without any manual action or container restart. Reload failures are caught and logged as warnings so a transient error cannot affect the download status (Issue #30).
- **Fixed:** Bundled TFLite fallback path in `_resolve_active_bird_model_spec` passed the configured model ID (e.g. `"medium_birds"`) to `_get_model_paths` instead of `"model.tflite"`, causing the fallback to look for a directory rather than the bundled model file and fail. The fallback now correctly searches for `model.tflite`.
- **Fixed:** ONNX models expecting `uint8` input (e.g. the bird-crop detector) received `float32` tensors, causing `INVALID_ARGUMENT` errors at inference time. The ONNX classifier now reads the model's declared input dtype from session metadata after load and returns raw `uint8 NHWC` tensors for quantized models, keeping the existing normalized `float32 NCHW` path for all others.
- **Fixed:** `small_birds_eu` (MobileNet V4 Large) is now correctly listed as GPU not supported. The model passes isolated OpenCL probes but consistently corrupts the GPU context with `CL_EXEC_STATUS_ERROR_FOR_EVENTS_IN_WAIT_LIST` when run after other GPU models in the same inference session — matching the same non-deterministic failure seen on `small_birds_na`. Intel GPU is no longer offered as a provider for this variant.

## [2.8.6] - 2026-03-24

- **Added:** Scheduled cleanup actions are now individually configurable. Three new toggles in Settings → Data allow "Remove Detections Without Clips", "Remove Detections Without Snapshots", and "Analyze Unknown Species" to run automatically as part of the existing 24-hour cleanup cycle. All default to off (opt-in). Manual action buttons are unchanged.
- **Added:** Pushover notifications now support device targeting. A new "Device(s)" field in notification settings accepts one or more comma-separated Pushover device names. Leave blank to send to all active devices (existing behaviour).
- **Added:** Notification language is now configurable in Settings → Notifications. A new "Notification Language" dropdown controls the language used for message text sent to Discord, Telegram, Pushover, and Email — independent of the UI language.
- **Added:** Gmail and Outlook OAuth app credentials (Client ID and Client Secret) are now configurable directly in Settings → Notifications → Email. Previously these could only be set via environment variables; they can now be entered and saved through the UI, unblocking the OAuth "Connect Gmail" / "Connect Outlook" flow for users without direct container access.
- **Added:** Reduced Motion and Zen Mode accessibility toggles are now wired in Settings → Accessibility. Both settings persist to the backend config and apply their respective CSS classes (`reduced-motion`, `zen-mode`) on load.
- **Fixed:** eBird CSV export now resolves English common names for species whose taxonomy cache only contains a localised name (e.g. Russian-locale users whose `taxonomy_cache` was populated with non-ASCII common names). A pre-enrichment pass runs before formatting rows: for each distinct scientific name where no English name was found via the existing SQL COALESCE chain, the exporter calls `get_localized_common_name(taxa_id, 'en')` which checks `taxonomy_translations` first (a single SQLite read per species when warm) and falls back to iNaturalist with `locale=en` only for species never previously exported or viewed in English. Concurrent lookups are capped at 5 to avoid thundering the iNat API on a first export.
- **Fixed:** MQTT stall detection now works for all deployments, including those without BirdNET-Go. Previously, the Frigate topic stall check required active BirdNET traffic as a liveness witness, so visual-only users had no self-healing mechanism if Frigate silently stopped publishing events. A new independent time-based watchdog task now runs alongside the MQTT message loop and periodically checks whether the Frigate topic has been silent for longer than `MQTT_FRIGATE_TOPIC_STALE_SECONDS` (default 5 minutes). When a stall is detected the watchdog disconnects the MQTT session immediately without exponential backoff, allowing fast recovery. The BirdNET-assisted check is preserved as a higher-confidence path that still triggers during the message loop for BirdNET users. Additionally, `_wait_for_handler_slot` now enforces a maximum total wait of `MQTT_MAX_HANDLER_WAIT_SECONDS` (default 120 s) so a flood of permanently-hung tasks can no longer block the MQTT message loop indefinitely. Both new limits are configurable via environment variables (Issue #22).
- **Fixed:** Video analysis failures caused by a Frigate timing race condition. When a Frigate `end` MQTT event fires before the event is committed to the Frigate API database, the auto video classifier's precheck (`GET /api/events/{id}`) received a transient 404 and immediately marked the detection as `video_analysis_failed`, counting toward the circuit breaker. After five such failures the circuit breaker opened and blocked all further video analysis. The precheck now retries up to 3 times with 2-second delays when a 404 is returned, resolving without error in the next poll once Frigate commits the event. All other error types (timeouts, 5xx, connection errors) still fail fast. Similarly, the MQTT-path snapshot fetch now retries once after 2 seconds before dropping the event as `classify_snapshot_unavailable`.
- **Fixed:** Safari/WebKit autofill crash on the login form. The `autofillFieldData.autoCompleteType.includes` null-reference error, which blocked login entirely when autofill was active, is resolved by adding explicit `autocomplete="username"` and `autocomplete="current-password"` attributes so WebKit can identify field types without hitting its internal null path.

## [2.8.5] - 2026-03-22

- **Added:** Three new ONNX models exported from the [Birder](https://github.com/birder-project/birder) pretrained model library and published to the GitHub models release, now downloadable and activatable via the Model Manager:
  - **FocalNet-B EU Medium** (`eu_medium_focalnet_b`) — 707 European bird species, 384px input, 338 MB. Strong birds-only accuracy for European feeders.
  - **HieraDeT DINOv2 Small Wildlife** (`hieradet_dino_small_inat21`) — 10,000-species iNat21 wildlife model, 256px, 159 MB. Lighter alternative to RoPE ViT or ConvNeXt for CPU-constrained setups.
  - **FlexiViT Global Birds** (`flexivit_il_all`) — 550 worldwide bird species, 240px, 85 MB. Fast and compact; good for regions without a dedicated regional model.
- **Added:** `scripts/export_and_config_birder_model.py` — utility script to download any Birder pretrained model, extract its preprocessing stats (`rgb_stats`, input resolution) from the checkpoint, export to ONNX, and write a `model_config.json` sidecar alongside `labels.txt`.
- **Added:** `scripts/eval_model_accuracy.py` — accuracy evaluation harness for ONNX bird classifiers. Supports CUB-200-2011 and labelled-directory datasets, threshold sweeping, per-class breakdown, inference timing, and JSON/CSV output.

- **Changed:** Default classification model changed from `MobileNet V2 (Fast)` (2019-era 960-class Google Coral TFLite) to `RoPE ViT-B14` for new installs. Users who have not changed their model setting were silently using a severely underpowered baseline; any install that already has a model selected is unaffected.
- **Fixed:** North America birds-only models (EfficientNet-B0 NA small, Binocular/DINOv2 NA medium) were configured with `direct_resize` preprocessing, which squashes Frigate's landscape-orientation snapshots into a square without cropping, significantly distorting bird shapes. Both are now set to `center_crop` with `crop_pct: 0.875`, matching the standard preprocessing used during training. When the bird-crop detector is active the effect is minimal (crops are already roughly square); on uncropped full-frame inference this is a meaningful accuracy improvement.
- **Fixed:** MobileNet V2 letterbox padding colour changed from grey (128) to black (0) to match the original Google Coral training preprocessing.
- **Added:** Each model in the registry now exposes a `recommended_threshold` field (0.45 for 10,000-class wildlife-wide models, 0.65 for birds-only families, 0.70 for the legacy MobileNet V2). Wildlife-wide models like ConvNeXt Large and EVA-02 naturally produce lower per-class scores due to competing against ~8,500 non-bird classes; the default 0.70 threshold was causing excessive "Unknown Bird" outcomes for these models. The recommended threshold is shown as an inline hint in the Model Manager detail panel so users know when to adjust it.

- **Fixed:** Frigate "clip not retained" stub responses (~78 bytes) are no longer cached as valid clip files. Every media-cache boundary now enforces a `512`-byte minimum (`_MIN_VALID_CLIP_BYTES`); sub-threshold bodies are rejected at write time, and any stub files already on disk are evicted at read time. This eliminates `icvExtractPattern` OpenCV crashes that surfaced as HTTP 500 errors when requesting video thumbnails for expired recordings.
- **Fixed:** The video thumbnail proxy endpoint (`/api/proxy/clip/…/preview`) now returns a clean HTTP 404 when Frigate returns a stub clip body instead of crashing inside the preview generator. The stub check mirrors the media-cache threshold so the two paths stay consistent.
- **Fixed:** Video classification could unconditionally override an "Unknown Bird" detection with any video result regardless of confidence, causing low-signal scores (e.g. 0.05) to replace a pending unknown label. A `_UNKNOWN_UPGRADE_MIN_SCORE = 0.10` floor is now enforced for the unknown-upgrade branch; the video classification columns are still written for UI display, only the primary label promotion requires the minimum score.
- **Fixed:** Image classification admission timeouts logged a `WARNING` for every queued request that timed out during bulk backfill, flooding logs when many workers raced the single background admission slot simultaneously. The first timeout per service instance is still logged at `WARNING`; all subsequent ones are demoted to `DEBUG`.
- **Fixed:** Workers waiting for a clip-not-retained snapshot classification slot could all fire at exactly the same instant during backfill, causing thundering-herd admission pressure. A random jitter (`0–500 ms`) is now inserted before the first snapshot admission attempt to spread the load.
- **Fixed:** Switching from the dev image back to the live image no longer breaks startup when the database contains Alembic revision identifiers unknown to the live migration tree. `init_db` now creates a timestamped pre-migration backup before every migration run, detects the "DB ahead of codebase" case when `alembic upgrade head` fails with an unknown-revision error, logs a clear recovery warning (including the backup path), and allows the backend to start safely. `_verify_schema` applies the same additive-schema tolerance so the ahead-case is handled consistently whether it is detected at migration time or schema-verification time.

- **Fixed:** `_resolve_color_space` in the classifier pipeline had inverted conditional logic that always returned `"RGB"` regardless of the value in the model spec, making it impossible to use any other color space (e.g. `"L"` for grayscale models). The function now correctly returns the spec value when it is a valid PIL classification mode and falls back to `"RGB"` otherwise. All current models use `"RGB"` so there is no runtime behavior change, but future models requesting a different color space will now be handled correctly.
- **Fixed:** TFLite float32 model normalisation was hardcoded to the MobileNet-style `(x - 127.5) / 127.5` formula regardless of the model spec. The classifier now reads `mean` and `std` from the preprocessing block and applies ImageNet-style per-channel normalisation when those values are present, falling back to the corrected MobileNet constant (`127.5 / 127.5`, previously the slightly-off `127.0 / 128.0`) for legacy float32 TFLite models without explicit stats. The only current TFLite model (`mobilenet_v2_birds`) is `uint8`-quantised and is not affected.
- **Fixed:** Taxonomy background sync was unconditionally forwarding `force_refresh=False` to `get_names` even when a forced refresh was not required. `AsyncMock` captured the keyword argument and caused two CI test assertions to fail. The kwarg is now only passed when `must_refresh` is `True`.

- **Added:** Reclassification overlay UI now dynamically displays the active inference provider icon and real-time backend RAM usage.
- **Changed:** Regional birds-only model variants now use generic functional names ("Small Birds", "Medium Birds") instead of strict geographic labels in the model manager.
- **Changed:** Removed the generic "Tiered model lineup" explanatory block from Detection Settings to reclaim vertical space.
- **Fixed:** Removed the absolute close button from the Reclassification overlay to prevent conflict with the primary modal close controls.
- **Fixed:** eBird CSV export date column now uses the eBird-standard `MM/DD/YYYY` format. Common names that were stored as scientific names (e.g. "Parus major" in the Common Name column after a manual tag by scientific name) are now correctly resolved to English common names; the taxonomy cache lookup additionally filters out entries where `common_name` equals `scientific_name` at the database level (Issue #23).
- **Fixed:** Species filters and the manual-tag dropdown in the Explorer no longer show duplicate entries for the same species under different name formats (e.g. "Great tit", "Great tit (Parus major)", "Parus major (Great tit)"). The species query now groups by canonical identity (`taxa_id` → `scientific_name` → display name) using the taxonomy cache to enrich missing IDs, and the Python deduplication layer also falls back through `scientific_name` before using the raw display value (Issue #26).
- **Fixed:** Weather unit system (`metric`, `imperial`, `british`) now applies correctly across all detection cards, the detection modal, the latest-detection hero, and the species chart for all users. Previously, when the owner settings were not yet loaded or the user was a non-owner, `"british"` was silently downgraded to `"metric"` because the legacy temperature-unit fallback maps `british → celsius → metric`; the fix inserts `authStore.locationWeatherUnitSystem` (correctly resolved from `/api/auth/status` for all users) as the primary fallback before the legacy field (Issue #24).

- **Fixed:** Explorer now keeps the desktop `Time`, `Species`, and `Camera` filters in a compact three-column layout instead of stretching each control full width, and the page-level bulk-tagging toggle is labeled `Multi Select` to better communicate its purpose.
- **Fixed:** Clicking the Dashboard navigation item while already on `/` now forces the dashboard view to remount and refresh, preventing stale summary content from lingering across repeated nav clicks.
- **Fixed:** Batch/manual video analysis snapshot fallback now uses the low-priority background image-classification path instead of the generic image path, retries temporary background-capacity pressure, and records overload as `background_image_overloaded` instead of incorrectly collapsing it into `snapshot_no_results`.
- **Fixed:** Snapshot-fallback video analysis now only records success when snapshot classification actually succeeds. Failed snapshot fallback no longer clears the video-classifier failure state by calling the success path unconditionally.
- **Fixed:** The classification admission coordinator now handles queue-timeout races more defensively and cancels rejected queued result futures instead of leaving unconsumed timeout exceptions behind, eliminating the noisy `Future exception was never retrieved` warnings seen during overloaded batch fallback runs.
- **Added:** The roadmap now puts a labeled feeder model evaluation harness at the top of the maintenance queue so crop defaults and model choices can be decided from real ground-truth feeder data instead of plausibility checks.
- **Added:** Detection Settings now lets owners override crop behavior and crop-source preference per model family and per regional variant, with shipped model-config defaults preserved underneath and high-quality snapshot preference available where crop generation is enabled.
- **Added:** YA-WAMF now manages the bird crop detector as a first-class downloadable artifact instead of assuming a manually placed local file. The detector has its own install status in the model manager, reuses the normal global download progress system, and crop controls stay blocked in the UI until the detector is installed.
- **Fixed:** Installed `model_config.json` crop settings now merge with registry defaults instead of replacing them wholesale, so newly added defaults like `source_preference=high_quality` survive older sidecars that only specify `enabled` or input-context fields.
- **Changed:** Downloaded model payloads are being standardized around a per-artifact `model_config.json` sidecar so preprocessing and provider metadata can travel with the installed model instead of relying on partially duplicated registry defaults.
- **Added:** Bird-crop generation is now model-config-driven. Classification entrypoints pass `is_cropped` source context end-to-end, the classifier can run a shared fail-soft crop stage before preprocessing, and the current North America birds-only manifests explicitly opt into that stage while Frigate `crop=True` paths skip double-cropping.
- **Added:** The bird-crop stage now autodiscovers a local ONNX detector from the standard models directory (for example `/data/models/bird_crop/model.onnx`) and still honors `BIRD_CROP_MODEL_PATH` as an override. If the detector is missing, unloadable, or returns unusable detections, classification falls back to the original image without breaking crop-enabled models.
- **Fixed:** Snapshot and video classification entrypoints now preserve `event_id` in classification input context through live MQTT handling, backfill, manual reclassification, and auto video fallback paths, so crop-source resolution can consistently locate higher-quality event snapshots when cropping is enabled on uncropped flows.
- **Fixed:** Video classification now preserves classification input context all the way through direct and subprocess worker paths, so batch analysis no longer drops `event_id` before crop-source resolution and crop-enabled models can actually use high-quality event snapshots during video/frame classification.
- **Fixed:** Event-driven video reclassification now forwards Frigate’s normalized `data.box` and `data.region` into classification input context, allowing crop-enabled models to use the original Frigate detection box as a reliable crop hint before falling back to the local crop detector.
- **Fixed:** `high_quality` crop-source preference now only upgrades the source used for crop generation. If no crop is found, YA-WAMF falls back to the original image/frame instead of silently classifying the full high-quality still image as a replacement input.
- **Changed:** The local bird-crop detector parser is intentionally strict: by default it only accepts simple detection tensors, rejects unsupported multi-class row layouts instead of guessing, and allows `cxcywh` coordinates only when `BIRD_CROP_BOX_FORMAT=cxcywh` is set.
- **Added:** The local bird-crop runtime now understands SSD-style ONNX detector signatures with `NHWC uint8` input and named `detection_boxes` / `detection_classes` / `detection_scores` outputs, which makes ONNX Model Zoo `ssd_mobilenet_v1_12-int8` a viable local crop-detector candidate.
- **Fixed:** Classifier preprocessing is now manifest-driven for ONNX/OpenVINO models, with explicit support for `letterbox`, `center_crop`, and `direct_resize` so models like Birder, timm iNat21, and Binocular no longer all inherit the same generic square-letterbox path.
- **Fixed:** Registry preprocessing metadata has been corrected for the currently known mismatch cases, including ConvNeXt Large iNat21, RoPE-ViT iNat21, Europe small/medium birds models, and EVA-02 Large.
- **Added:** Birds-only ONNX export tooling now writes `model_config.json` next to `model.onnx` and `labels.txt`, capturing source model preprocessing defaults for release-backed artifacts.
- **Changed:** Small and medium ONNX model slots are being reworked toward birds-only replacement artifacts published via GitHub Releases, with validation tracked in [`docs/plans/2026-03-19-birds-only-model-validation-matrix.md`](docs/plans/2026-03-19-birds-only-model-validation-matrix.md).
- **Changed:** The experimental wildlife-wide small and medium ONNX placeholders (`hieradet_small_inat21` and `rope_vit_b14_inat21`) now live in the advanced overflow instead of the default recommended lineup.
- **Added:** Detection Settings now includes a `Bird model region` override (`Auto`, `Europe`, `North America`) wired end-to-end through the UI settings payload so regional birds-only families can be selected manually while location-based auto-selection remains the default.
- **Added:** New backend exporter [`backend/scripts/export_binocular_model.py`](backend/scripts/export_binocular_model.py) supports converting the North America `jiujiuche/binocular` NABirds checkpoint into ONNX plus labels for release-backed artifact testing.
- **Added:** Candidate birds-only release assets have been uploaded for Europe small (`MobileNetV4`), Europe medium (`ConvNeXt V2 Tiny 256px`), North America small (`n2b8/birdwatcher` EfficientNet-B0 NABirds), and North America medium (`Binocular` / `DINOv2 ViT-B/14`) under the `models` release for side-by-side validation before any registry swap.
- **Changed:** The `models` GitHub release notes now document the regional `small_birds` / `medium_birds` candidate assets and their label behavior so release-backed testing matches the current birds-only replacement plan.
- **Added:** Classifier runtimes now support optional grouped-label collapse strategies, allowing NABirds-style North America checkpoints with `555` visual categories to be surfaced as deduplicated species results by collapsing trailing parenthetical variants into `404` species labels.
- **Changed:** Regional birds-only model families are now resolved end-to-end through the model manager. `small_birds` and `medium_birds` can install as multi-variant family directories, expose the correct active regional artifact based on `Auto | Europe | North America`, and pass variant-specific runtime metadata like `input_size`, `weights_url`, and `label_grouping` through to the classifier service.
- **Changed:** Container-backed validation in the running `yawamf-backend` image now confirms the Europe small and medium birds-only candidates produce finite outputs on ONNX Runtime CPU, OpenVINO CPU, and OpenVINO GPU, while the current North America small and medium NABirds candidates still fail the OpenVINO GPU correctness gate by returning non-finite outputs after successful GPU compilation.
- **Fixed:** North America regional birds-only candidates no longer advertise or auto-select `intel_gpu`. The registry now marks those artifacts as `cpu`/`intel_cpu` only, and runtime selection honors that constraint so `auto` stays on OpenVINO CPU instead of loading known-bad GPU paths.
- **Added:** Detection Settings now presents a tiered model lineup with downloadable small, medium, large, and advanced wildlife models, plus guidance that keeps advanced options collapsed by default for most installs.
- **Added:** Model downloads now appear in the global progress system so owners can track long-running ONNX artifact downloads from anywhere in the UI.
- **Changed:** The new model picker, download progress messaging, and adjacent Detection Settings guidance are now localized across all supported UI languages instead of falling back to English outside the default locale.
- **Fixed:** Birder wildlife model labels are now normalized to canonical scientific names instead of leaking raw taxonomy-path strings like `04853_Animalia_...` into detections, video analysis, and release label assets.
- **Fixed:** Taxonomy repair and manual species updates now backfill canonical scientific/common names more robustly by preferring stored taxonomy identifiers and scientific names over localized display labels.

- **Fixed:** Selecting a new classification model (e.g., EVA-02 Large) now immediately restarts the subprocess worker pool. Previously, workers would continue using the old model until they crashed or were manually restarted, causing a mismatch between the UI and actual inference results.
- **Fixed:** Removed legacy "safety" remapping that automatically downgraded EVA-02 Large to ConvNeXt Large when not explicitly flagged. The system now strictly respects the user's active model selection.
- **Fixed:** Improved system stability when using large models (EVA-02) by increasing default classification timeouts to 60s (from 30s) and worker ready timeouts to 60s (from 20s). This prevents "classify_snapshot_timeout" errors during the initial heavy model load phase and reduces unnecessary OOM-related worker restarts.
- **Fixed:** Added a global initialization lock to the classifier supervisor. This ensures that only one worker across all pools (Live, Video, Background) can load its model at a time, eliminating massive RAM and GPU spikes that previously led to system-wide OOM crashes and GPU resource exhaustion errors when starting up with "Elite" models.
- **Fixed:** Prevented API timeouts (504 Gateway Timeout) when switching to heavy models by moving the worker pool restart process into FastAPI background tasks, ensuring the UI remains responsive even if workers take minutes to load the new model into GPU memory.
- **Fixed:** Resolved a race condition where the supervisor watchdog loop could attempt to replace a crashed worker simultaneously with an intentional pool restart, which previously resulted in "zombie" leaked worker processes running in the background.
- **Fixed:** Increased the `asyncio` subprocess stream reader limit to 512KB. This hardens worker communication against oversized stdout protocol messages and large stderr bursts, reducing `LimitOverrunError` risk when workers emit large result payloads or runtime error output.
- **Changed:** The Video Classifier now stops starting new batch analysis jobs whenever live detections are running or queued, while allowing any already-running video analysis to drain normally. This prioritization reduces GPU and RAM contention for immediate detections when using heavy "Elite" models under sustained load.
- **Changed:** `In-Process` is now the default image execution mode for fresh installs and unset configurations. This substantially reduces RAM usage with larger models by sharing model weights in one backend process, while `Subprocess` remains available for users who prefer stronger isolation.
- **Changed:** Optimized memory usage in the main process by preventing it from loading the bird classification model into RAM when configured for `subprocess` execution mode. Model loading is now deferred entirely to the dedicated worker processes.
- **Fixed:** eBird CSV export now robustly falls back to scientific names in the "Common Name" column if no English common name is available in the taxonomy cache. This ensures better compatibility with eBird's strict import validation.
- **Fixed:** Corrected a bug in the taxonomy service where localized species names (e.g., Russian) were incorrectly overwriting canonical English names in the main cache, which previously broke English-only exports like eBird. Localized names are now correctly stored only in the translation table.
- **Added:** New **Execution Mode** toggle in Settings -> Detection. This allows users to switch between `Subprocess` (isolated and stable) and `In-Process` (shared RAM) classification. Switching to In-Process can reduce backend RAM usage by up to 60% (from ~11GB to ~4GB) when using "Elite" accuracy models by sharing a single model instance across all inference tasks.
- **Fixed:** Video classification progress now accurately reaches 100% in the UI overlay even for short videos or when some frames are skipped due to inference errors.
 The frontend now correctly trusts the backend's frame total instead of sticking to the configured maximum, and progress callback signatures were hardened to prevent internal reporting mismatches.
- **Fixed:** Concurrent manual video reclassifications now correctly track their progress independently in the UI. Previously, triggering multiple manual reclassifications simultaneously caused their progress bars to violently overwrite each other in the notification center.
- **Fixed:** The global progress banner during Batch Analysis will no longer jump backward or display misleading totals. The UI previously confused per-worker video frame ticks with overall queue item counts, causing the progress denominator to fluctuate dynamically as workers picked up new events. Batch progress now correctly stabilizes on "Items" using the authoritative backend queue status.
- **Fixed:** Resolved a critical pre-assignment deadlock in the subprocess classifier supervisor that could permanently stall live Frigate MQTT ingestion (Issue #22). If a worker process crashed during startup (e.g. GPU initialization failure) and the pool was previously active, the supervisor would block incoming classification requests indefinitely waiting for an idle worker, preventing the admission coordinator from shedding load and wedging the pipeline at 0% capacity.
- **Fixed:** Subprocess classification requests now actively track unassigned futures and fail immediately if 0 active workers are available after a recovery attempt. This enables rapid failure propagation, correctly triggering the supervisor's circuit breaker and unblocking upstream admission queues to recover live event flow.
- **Changed:** eBird export now follows the reopened issue-23 follow-up contract: protocol is `Stationary`, duration is populated per exported date window, submission comments include available runtime metadata and confidence, export uses explicit location `state` / `country` settings when provided, and the UI now supports inclusive `From` / `To` export dates instead of a single-date picker.
- **Changed:** The eBird export range UI now has an explicit `Export everything` toggle that clears and disables the `From` / `To` pickers when enabled, making full-export state obvious instead of relying on blank date fields.
- **Changed:** The Notifications `Errors` tab now surfaces backend-recorded failures only in its live incident list and grouped diagnostics. Frontend/client polling issues remain available in captured diagnostic bundles, but no longer clutter the live error workspace.
- **Changed:** eBird export is now stricter and importer-safer: `Unknown Bird` rows are always excluded, localized/non-English fallback names are suppressed unless the exporter can resolve an English-safe common name, and the route remains a single 19-column Record Format path.
- **Added:** Location settings now include optional `state` / `country` values so eBird export can fill those columns without guessing from coordinates.
- **Changed:** Notifications jobs surfaces are now much more compact. The global progress banner and Jobs view default to short, direct status text and only show extra detail when a job is blocked, stale, or otherwise needs explanation.
- **Fixed:** `/api/ebird/notable` no longer returns `500 Internal Server Error` when optional taxonomy thumbnail enrichment fails. The route now imports its enrichment dependencies correctly and treats thumbnail lookup as best-effort so notable observations still load.
- **Changed:** Notifications Jobs and the global progress banner now explain what background work is actually doing. Active rows show explicit activity, determinate vs indeterminate progress, freshness, and blocker text instead of unlabeled bars.
- **Added:** Reclassification queue telemetry now surfaces truthful capacity details in the UI, including worker-slot usage, queue-slot availability, and MQTT-pressure throttling context where available.
- **Added:** Deep Video Analysis now persists the model id used for completed video-classification results, exposes a backend-derived friendly model name in event APIs, and shows both provider (`CPU` / `GPU`) and model chips in the Detection Details video-analysis card.
- **Fixed:** Intel iGPU OpenVINO stability now uses `openvino==2024.6.0` as the last verified working runtime line for the live ConvNeXt bird model on this host. Earlier investigation showed `2026.x` broke GPU device discovery and `2025.4.1` still produced non-finite GPU outputs for the live ConvNeXt path despite `f32`, cache, and stream hardening.
- **Changed:** The repo now treats OpenVINO runtime drift as a first-class regression risk. The durable incident backstory, misleading intermediate symptoms, and final runtime findings are documented in [docs/plans/2026-03-13-openvino-gpu-regression-retrospective.md](docs/plans/2026-03-13-openvino-gpu-regression-retrospective.md) so future debugging does not repeat the same archaeology.
- **Fixed:** Backfill/unknown-analysis GPU regressions are now understood: the earlier `already_exists` skip symptom on the restored branch was actually a non-finite-score path hidden by SQLite `INSERT OR IGNORE`; the investigation now documents why that happened and why it was not a true duplicate-event condition.
- **Fixed:** Subprocess-mode live and background bird image classification now runs behind the same `ClassificationAdmissionCoordinator` used by in-process execution. This restores bounded admission, fast overload shedding, and lease-expiry recovery for the default `subprocess` runtime instead of letting requests wait indefinitely behind busy or wedged worker slots.
- **Fixed:** When a coordinated subprocess image-classification lease expires, YA-WAMF now aborts the matching supervised worker assignment using coordinator-owned `work_id` and `lease_token`, forcing prompt worker replacement. This prevents stale subprocess work from holding the only live slot after the coordinator has already recovered logical capacity.
- **Added:** Regression coverage now asserts subprocess-mode fast live overload behavior, truthful live in-flight status reporting, stale-capacity reclaim, and supervisor-side abort semantics for matching vs stale lease tokens.
- **Fixed:** GPU inference stability on Intel hardware is now significantly improved by forcing `f32` (FP32) precision. This prevents OpenVINO from defaulting to FP16, which caused mathematical overflows (`NaN`/`inf` logits) on un-quantized bird models, resulting in "produced no finite probabilities" errors and triggering unnecessary CPU fallbacks.
- **Fixed:** GPU concurrency is now limited to a single stream per worker via `NUM_STREAMS: 1` (corrected from `GPU_THROUGHPUT_STREAMS`). This prevents Intel OpenCL driver race conditions and resource exhaustion during concurrent batch reclassification tasks.
- **Fixed:** Subprocess classifier workers now forward their `stderr` logs to the main backend log. This ensures that GPU initialization errors, driver warnings, and OpenVINO startup failures are now visible in standard `docker logs` for better troubleshooting.
- **Fixed:** OpenVINO GPU shader compilation is now cached in `/tmp/openvino_cache` via the `CACHE_DIR` property. This prevents worker processes from timing out during heavy initial model loads and avoids the `worker startup timed out` errors previously seen during large batch jobs.
- **Fixed:** The Svelte global `ErrorBoundary` now filters out harmless, non-fatal exceptions (including `Cloudflare connection failed`, `Failed to fetch`, and `ResizeObserver loop limit exceeded`), preventing browser extensions or transient network drops from hijacking the UI with full-screen crash cards.
- **Fixed:** The `GlobalProgress` bar and `Jobs` view are now consistent during batch reclassifications. The main "Batch Analysis" job card no longer disappears when individual video classification sub-jobs start, and the global percentage no longer jumps erratically by excluding individual frame progress from the overall event-queue sum.
- **Fixed:** OpenVINO runtime exceptions (like `CL_OUT_OF_RESOURCES`) are now properly raised as `InvalidInferenceOutputError` instead of being silently swallowed as empty results. This allows the supervisor to accurately detect crashed workers and reboot them, preventing permanent hangs in the batch processing queue.
- **Added:** Detection backfill jobs now broadcast their started status to the UI immediately. Users now receive instant feedback (e.g. "Querying Frigate API...") during the expensive initial data-sync phase before the first event is processed.
- **Added:** The Detection Details video-analysis card now displays explicit `GPU` or `CPU` badges. This provides owners with real-time verification of the hardware acceleration path used for each verified detection.
- **Changed:** Historical note: `openvino==2025.4.1` was an intermediate compatibility pin that restored GPU device enumeration versus `2026.x`, but it was later found to remain numerically unstable for the live ConvNeXt Intel iGPU path on this host.

- **Fixed:** Video classification now rejects degenerate near-uniform confidence outputs (for example top score near `1 / class_count`) as `video_no_results` instead of reporting a misleading `completed` result with ~`0%` confidence, and uses deterministic full-clip stratified frame sampling with best-frame aggregation to improve transient-bird recovery.
- **Added:** Detection video results now persist per-event inference runtime evidence (`video_classification_provider`, `video_classification_backend`) through DB/API/UI so GPU vs CPU execution is attributable on each classified event instead of inferred from process-global status.
- **Fixed:** Frontend `svelte-check` now passes for the strict non-finite debug toggle by adding `strict_non_finite_output` to the UI `Settings` API type, aligning typed settings reads/writes with the backend-exposed field.
- **Added:** Experimental strict-non-finite classifier toggle is now configurable end-to-end: backend setting `classification.strict_non_finite_output` (env override `CLASSIFICATION__STRICT_NON_FINITE_OUTPUT`, with legacy `CLASSIFIER_STRICT_NON_FINITE_OUTPUT` fallback) is exposed in `Settings > Debug`, persisted via `/api/settings`, and surfaced in `/api/classifier/status` as `strict_non_finite_output` so active policy is explicit during controlled GPU/CPU behavior tests.
- **Fixed:** Detection Details video-analysis inference markers now use inline SVG GPU/CPU icons instead of font-dependent glyph characters, so provider markers render consistently across browsers/platform fonts.
- **Fixed:** Subprocess classifier supervision now supports a dedicated background worker hard deadline (`classification.background_worker_hard_deadline_seconds`, env `CLASSIFICATION__BACKGROUND_WORKER_HARD_DEADLINE_SECONDS`, default `120s`) instead of forcing background/backfill jobs to share the shorter live deadline; this prevents long-running historical classification work from repeatedly tripping `hard_deadline` restarts and opening the background worker circuit while preserving strict live-request deadlines.
- **Added:** Detection Details video-analysis card now shows a live inference-provider badge (`GPU` / `CPU`) during active analysis by polling classifier status, so owners can immediately see whether current processing is running on accelerated or fallback compute.
- **Added:** Auto video-classifier diagnostics now include classifier runtime context (`inference_backend`, `active_provider`, `selected_provider`, and latest runtime-recovery snapshot when available), so exported incident evidence shows which inference path was active when failures occurred.
- **Changed:** GPU runtime recovery policy is now more robust: on invalid OpenVINO GPU output, YA-WAMF now retries once on a freshly reloaded GPU model before demoting to CPU fallback, and workers that fell back to OpenVINO CPU now auto-attempt GPU restoration after a cooldown (when GPU is configured/available) instead of staying on CPU indefinitely.
- **Added:** Classifier status telemetry now includes GPU recovery counters (`runtime_gpu_retries`, restore attempts/success/fail, and restore cooldown marker) so owner diagnostics can verify whether the system is actually recovering back to GPU over time.
- **Changed:** Backend dependency pinning now treats the OpenVINO version as host-sensitive and regression-prone; the newer investigation found `2024.6.0` to be the last verified working Intel iGPU runtime line for the live ConvNeXt model on this host, replacing the earlier assumption that `2025.4.1` was the stable baseline.
- **Added:** New backend regression test (`backend/tests/test_dependency_pins.py`) asserts the OpenVINO pin remains fixed, preventing accidental drift back to an unbounded OpenVINO version range.
- **Fixed:** Subprocess video-classification progress callbacks now accept both keyword and positional callback signatures (`current_frame`/`total_frames` and legacy positional args), restoring reliable `reclassification_progress` SSE emission for frame-strip UI updates during reclassify/auto-video runs.
- **Added:** Location weather units now support a third `british` mode (`°C`, `mph`, `mm`) across backend settings/auth payloads and frontend weather rendering/helpers, so UK-style mixed units can be selected globally without temperature/speed/precipitation mismatches.
- **Fixed:** OpenVINO GPU runtime failures (for example `CL_OUT_OF_RESOURCES`) are no longer silently treated as empty classifier output. OpenVINO classify/classify_raw paths now surface these as invalid-runtime errors so classifier runtime recovery can immediately fail over to a safer backend/provider (typically Intel CPU) instead of cascading into repeated `video_no_results` failures and circuit-breaker opens.
- **Fixed:** Auto video analysis no longer collapses into `video_no_results` when progress delivery is slow: worker-side progress emission is now best-effort, video classification no longer treats progress callback failures as fatal, and supervisor progress callbacks no longer block worker result consumption behind slow SSE/broadcast handling.
- **Fixed:** Owner incident detail now shows grouped diagnostics for the selected incident even when the evidence exists only in backend diagnostics; backend-only incidents like `video_no_results` no longer render an empty “Grouped Diagnostics” panel just because no matching local frontend group exists.
- **Changed:** GitHub Actions now opts JavaScript actions into Node 24, uses the newer checkout/setup-node actions, gives workflow runs explicit commit-based run names, and always builds/publishes the frontend and backend images together on `dev` so both `:dev` containers share the same git hash for deployment tracking.
- **Added:** Owner Errors workspace now has a real “Clear Live Errors” path: the backend exposes an owner-only diagnostics clear endpoint, the frontend clears persisted local diagnostics and resets correlated incidents, and the page refreshes against empty backend history instead of leaving stale evidence with no way to reset it.
- **Fixed:** Supervised video OpenVINO startup is now less fragile on GPU hosts: worker pools warm sequentially instead of compiling multiple video workers in parallel during cold start, and video workers get a larger ready timeout than live/background workers so heavy OpenVINO initialization does not fail under the short image-worker startup budget.
- **Fixed:** Detection backfill now treats classifier worker transport loss and transient background-worker restarts as bounded retryable failures instead of leaking raw connection-reset errors or immediately losing the event; send-time worker transport failures are normalized into worker-unavailable errors, dead workers are replaced before reuse, and backfill gets a larger per-event budget with one transient retry for background worker timeout/startup/unavailable conditions.
- **Fixed:** Owner incident correlation now resolves stateful health incidents against the latest backend health snapshot instead of leaving them permanently open; cleared video/classifier circuit-breaker incidents move to recent history, and active root-cause incidents like `video_no_results` remain visible in Current Issues after recovery.
- **Added:** Global weather measurement units setting for issue `#24`: `Settings > Integrations > Location` now uses a single `metric`/`imperial` preference, older `location.temperature_unit` configs auto-migrate on load, and auth/settings payloads expose the canonical unit-system field while keeping the legacy temperature alias for compatibility.
- **Changed:** Weather rendering now uses one shared frontend unit helper across detection cards, the latest-detection hero, the detection modal, and species weather charts so temperature, wind, and precipitation stay consistent instead of mixing `°F` with `km/h` or `mm`.
- **Fixed:** Auto video classification now uses a video-specific supervised worker deadline instead of the shorter live-image worker deadline, preserves worker failure reasons (deadline/startup/exit/circuit) instead of flattening them into generic “no results”, and records canonical backend diagnostics for video failures/circuit-open events so the owner Errors workspace can surface them.
- **Added:** Owner incident workspace in Notifications > Errors now correlates backend diagnostics into current/recent incidents, preserves richer evidence in exported bundles, and generates issue-ready report text with optional owner notes for GitHub reporting.
- **Changed:** OpenVINO/GPU bird inference is now fully supervisor-oriented in subprocess mode: the main backend no longer eagerly loads a duplicate bird model, status probes are cached instead of re-running OpenVINO device detection on every refresh, and owner bird test/debug routes use subprocess-safe behavior instead of assuming an in-process bird runtime.
- **Fixed:** Classifier self-healing is more robust under worker replacement failures: failed restarts no longer kill the watchdog loop, unavailable slots are tracked explicitly, restart budgets still trip circuit breakers, and recovery telemetry now includes worker-reported runtime fallback events.
- **Added:** Supervised video bird classification now uses a dedicated worker pool and protocol support for progress events, isolating clip analysis from live/background snapshot workers while preserving progress callbacks and worker-side runtime recovery reporting.
- **Fixed:** Batch reclassification UI now self-heals from the authoritative owner queue status: the app shell polls `/api/maintenance/analysis/status` globally, recreates a synthetic batch job for the global progress bar after refresh/SSE loss, settles stale `Batch Analysis` process notifications when the queue drains, and avoids duplicate batch-vs-event progress counting when per-event reclassification jobs are already active.
- **Changed:** eBird CSV export now targets the strict eBird record-format workflow: it emits headerless 19-column rows, accepts an optional single-day `date` filter, prefers English taxonomy names for species labels, and no longer requires eBird API enablement or credentials just to export local detections.
- **Fixed:** eBird export now validates the `date` query before streaming begins, avoids duplicate rows when taxonomy cache aliases share a `taxa_id`, and treats corrupt score metadata as best-effort provenance so one bad historical row cannot break the full CSV download.
- **Fixed:** Classifier subprocess workers no longer let bootstrap/runtime logs corrupt the stdout protocol stream: normal worker logs are redirected to stderr, the client tolerates stray stdout noise defensively, and live/backfill classification no longer fails startup with misleading `exited before ready` errors when TensorFlow/OpenVINO emits initialization chatter.
- **Fixed:** Background classifier subprocesses now accept large historical snapshot payloads during detection backfill by raising the worker stdin stream limit above the default asyncio line cap, preventing `Separator is not found, and chunk exceed the limit` crashes on base64-encoded Frigate snapshots.
- **Fixed:** Classifier supervisor cold-start no longer drops the first live/backfill requests while OpenVINO workers are still loading: worker pools now start lazily per priority instead of booting every pool on first use, workers in the requested pool start in parallel, startup-ready waits are configurable and mapped to explicit worker-unavailable handling, and backfill error logs now preserve exception type/details instead of empty `TimeoutError` strings.
- **Fixed:** Detection/weather backfill is now more truthful and more complete: historical Frigate event fetches paginate beyond the previous 100-event cap, historical filtering now uses Frigate score parity with live processing, async backfill jobs track structured `error_reasons`, and diagnostics now capture snapshot/classifier/job failure reasons instead of collapsing them into generic backfill errors.
- **Added:** Issue `#22` classifier resilience hardening: a live/background admission coordinator with lease reclaim and stale-completion rejection, recovery-aware ML/event-pipeline health reporting, richer diagnostics export, and truthful paused/throttled backfill progress messaging.
- **Added:** New subprocess classifier-supervisor foundation behind `classification.image_execution_mode`, including worker config/settings, a framed worker protocol, worker-process and worker-client primitives, supervised live/background pools, watchdog-based worker replacement, restart-budget circuit breaking, and initial `ClassifierService` routing hooks for subprocess image execution.
- **Changed:** Subprocess classifier execution can now boot a real worker entrypoint via `python -m app.services.classifier_worker_process`, and supervisor failure modes are translated back into existing live-pipeline semantics so circuit-open conditions surface as explicit overload and worker heartbeat/deadline failures surface as lease expiry instead of leaking raw supervisor exceptions.
- **Changed:** Event processing now coalesces duplicate in-flight live Frigate event IDs and sheds stale live events before snapshot classification, reducing wasted live-classifier capacity during replay storms or delayed MQTT delivery.
- **Fixed:** Live-event shedding now keys off MQTT receipt age rather than raw Frigate event start time, and duplicate-event coalescing is limited to the classification section so reconnect backlogs are not discarded and downstream save/notify stalls do not suppress legitimate retries.
- **Fixed:** Non-finite classifier scores are now sanitized or rejected before thresholding/persistence, preventing OpenVINO `NaN` outputs from being misreported as “already exists” during detection backfill and unblocking downstream weather backfill when historical detections are rebuilt.
- **Fixed:** Classifier runtime recovery now treats non-finite model outputs as backend failure, automatically falling back off broken providers (for example OpenVINO GPU to CPU/ONNX/TFLite), surfacing recovery in health/status telemetry, and using the correct TFLite asset paths if an ONNX/OpenVINO fallback chain reaches TFLite.
- **Changed:** Image classification now defaults to supervised `subprocess` execution instead of in-process threads, so issue `#22` worker replacement/circuit-breaker self-healing is active by default unless a deployment explicitly opts back into `in_process`.
- **Fixed:** Subprocess classifier workers now drain and retain a bounded stderr tail, preventing pipe backpressure from wedging workers and surfacing recent worker stderr in supervisor metrics/startup failures for easier diagnosis.
- **Changed:** Health/backfill/diagnostics now surface subprocess worker-pool recovery state end-to-end: `/health` includes worker-pool circuit data, backfill progress messaging distinguishes worker recovery from ordinary live throttling, and exported diagnostics bundles preserve worker restart/circuit evidence plus ignored late worker results.
- **Changed:** App shell refactor extracted mobile top-bar UI and stale reclassification recovery orchestration into dedicated modules, reducing `App.svelte` to a slimmer route/layout coordinator.
- **Changed:** Legacy API-key fallback auth helpers were consolidated into `app/auth.py`, and router/main imports now use the unified auth module.
- **Removed:** Deprecated `backend/app/auth_legacy.py`; legacy API-key behavior remains supported via `get_auth_context_with_legacy` in `app/auth.py`.
- **Added:** Jobs page now includes a top pipeline flow view (`Queued → Running → Outcomes`) with per-kind stage counts so background work is visible at a glance.
- **Changed:** Jobs pipeline now uses real queue telemetry for auto video reclassification (`pending`/`active`) and explicitly marks queue depth as “not reported” for job kinds that do not expose queue metrics yet.
- **Fixed:** Jobs queue telemetry polling now keeps retrying after transient failures and preserves previously known queue data instead of downgrading to “not reported.”
- **Changed:** Notifications workspace heading now reads “Notifications & Jobs” to better match the combined page purpose.
- **Added:** Notifications workspace now has a dedicated `Errors` tab (alongside Notifications and Jobs) with grouped anti-spam diagnostics, severity tagging, and drill-down metadata for troubleshooting.
- **Added:** Client-side diagnostics bundle capture/archive in the `Errors` tab so multiple support bundles can be stored and downloaded independently as JSON.
- **Added:** Diagnostics export payloads now include app version/branch/hash metadata plus captured health snapshots with event-pipeline latest timeout/failure/drop details.
- **Fixed:** Ongoing process notifications now auto-settle when no active backing job is tracked, preventing Notifications/Jobs drift after reconnects or missed terminal updates.
- **Fixed:** Taxonomy repair now skips `Unknown Bird`/unknown-label detections so unresolved catch-all labels no longer appear as perpetual taxonomy work items on every sync run.
- **Changed:** Completed locale-key coverage pass for the Notifications/Jobs/Errors workspace additions (pipeline labels, Errors tab strings, bundle controls), including updated localized Notifications page headings.
- **Added:** New UI locale regression test (`locales.jobs-errors.test.ts`) to enforce key coverage for Notifications/Jobs/Errors strings across all supported languages.
- **Added:** Settings polling failures for analysis status and backfill status are now captured into the Errors diagnostics store for exportable troubleshooting context.
- **Added:** New owner-only backend diagnostics history endpoint `GET /api/diagnostics/errors` with bounded in-memory retention, plus structured event capture for event-pipeline drops/timeouts/failures and notification-dispatcher queue/job failures.
- **Fixed:** Jobs pipeline no longer shows idle reclassification queue rows after local clear actions when queue depth is `0` and no job activity exists.
- **Fixed:** Reclassification fallback handling now treats `pending` as queued (not active running), preventing phantom extra active reclassify jobs beyond configured concurrency during batch analysis.
- **Fixed:** Jobs/Global Progress active counts now exclude stale reclassification entries, so displayed running concurrency aligns with backend-reported active workers instead of stale UI remnants.
- **Changed:** Auto video `trigger_classification` now uses the same bounded/deduped queue path as batch analysis (instead of direct task spawn), preventing concurrency oversubscription races between trigger and queue workers.
- **Changed:** Video-analysis queue hardening: pending queue is now truly bounded (`asyncio.Queue(maxsize)`), enqueue dedupe is guarded by an async lock for concurrent safety, pending-id lifecycle avoids dequeue/start race windows, and status snapshots prune completed tasks before reporting active counts.
- **Fixed:** Live MQTT snapshot classification now runs on a dedicated live-image executor instead of the shared non-live image pool, preventing user-initiated or batch snapshot work from queueing ahead of real-time Frigate events under load.
- **Changed:** Event-pipeline health status is now recovery-aware: cumulative critical-failure counters remain available for diagnostics and soak analysis, while `/health` can return to `ok` after the configured recovery window if no new critical failures occur.
- **Fixed:** Backend app shutdown now explicitly tears down classifier executors, preventing unmanaged image/video worker threads from lingering across process teardown or test/service reinitialization.
- **Changed:** Event-pipeline recovery now stays `degraded` while unresolved incomplete events remain after a critical failure, avoiding overly optimistic `/health` recovery during partial pipeline drain.
- **Added:** High-quality event snapshots now have a configurable derived JPEG quality setting (default `95`) in Data Settings, so users can trade off snapshot detail against file size without changing image format compatibility.
- **Fixed:** Reclassification recovery now also reconciles older `running` jobs (not just `stale`) against backend classification status, reducing phantom Active entries when SSE terminal events are missed.
- **Added:** Dedicated frontend background-job telemetry store (`jobProgressStore`) with explicit lifecycle states (`running`, `stale`, `completed`, `failed`), rate-per-minute estimation, and ETA tracking.
- **Changed:** Notifications now hosts a unified tabbed workspace for both notification history and jobs (`/notifications` + `/notifications/jobs`), with `/jobs` retained as a legacy canonical redirect to the Jobs tab.
- **Changed:** Global progress UI now reads from dedicated job telemetry (not notification `process` items), supports determinate/indeterminate rendering, exposes stale/update-age indicators, and links directly to the Notifications Jobs tab.
- **Changed:** Backfill and reclassification SSE/polling paths now update both notification history and job telemetry in parallel, improving resilience when terminal SSE events are missed.
- **Fixed:** Backfill progress reconciliation no longer treats `null` status as implicit completion; matching jobs are now marked `stale` defensively to avoid false-finished states during restarts/auth races.
- **Fixed:** Job telemetry updates now preserve prior counters when sparse payloads omit `current`/`total`, enforce monotonic progress, and prevent `N/0` terminal-state regressions.
- **Changed:** Added locale-key coverage for new Jobs/global-progress/navigation/shortcut strings across all supported UI languages.
- **Added:** Frontend unit tests for job telemetry edge cases (sparse payloads, monotonic counters, stale transitions, idempotent prefix-close behavior, terminal counter normalization) via Vitest.
- **Added:** Owner API endpoint `GET /api/events/{event_id}/classification-status` for authoritative per-event video-classification state (`status`, `error`, `timestamp`) during client recovery flows.
- **Fixed:** iOS PWA stale-reclassification drift now self-heals by reconciling stale `reclassify:*` jobs against backend classification status on app resume/reconnect/interval, aligning PWA behavior with Safari fresh-session state.
- **Added:** Frontend + backend regression tests for reclassification fallback terminal transitions and classification-status API behavior.

- **Changed:** Refactored backend configuration internals into segmented modules: `app/config.py` (orchestration), `app/config_models.py` (settings models/defaults), and `app/config_loader.py` (env/file merge logic), reducing `config.py` from 1,032 lines to 95 lines while preserving `from app.config import settings` compatibility.
- **Added:** New backend regression tests for env-to-settings mapping coverage (`backend/tests/test_config_env_mapping.py`).
- **Fixed:** Restored env override support for `CLASSIFICATION__VIDEO_CLASSIFICATION_TIMEOUT_SECONDS`, `CLASSIFICATION__VIDEO_CLASSIFICATION_STALE_MINUTES`, and `NOTIFICATIONS__NOTIFICATION_COOLDOWN_MINUTES`.

- **Added:** New `classification.write_frigate_sublabel` setting (API + config + env: `CLASSIFICATION__WRITE_FRIGATE_SUBLABEL`) to control whether YA-WAMF writes species labels back to Frigate event sublabels.
- **Added:** Detection Settings now includes a visible toggle for `write_frigate_sublabel`, with localization coverage across all supported UI languages.
- **Changed:** Event processing now honors `write_frigate_sublabel`; Frigate write-back is skipped when disabled while local YA-WAMF detections still persist normally.
- **Changed:** Snapshot classification now applies a stricter confidence gate when Frigate sublabel disagrees and Frigate trust is disabled, reducing overconfident cross-species mislabels (for example long-tailed tit drift) by demoting low-confidence disagreements to `Unknown Bird`.
- **Changed:** Legacy `active_model.json` entries that reference `eva02_large_inat21` without explicit user selection now auto-remap to `convnext_large_inat21` on load; explicit EVA selections remain supported.
- **Fixed:** Frontend nginx now serves `/assets/*` with strict file lookup (`404` if missing) instead of SPA fallback to `index.html`, preventing module MIME errors (`text/html` returned for JavaScript chunks) after rolling updates.

- **Fixed:** MQTT ingestion now dispatches Frigate/BirdNET message handling through bounded concurrent workers so long-running event processing no longer blocks topic intake in a single serial loop.
- **Changed:** Real-time Frigate event handling now ignores routine `update`/`end` chatter and processes actionable bird events (`new` and false-positive cleanup), reducing duplicate classification passes per Frigate event ID.
- **Fixed:** MQTT worker handlers now enforce per-message timeouts, preventing stalled Frigate/BirdNET processing tasks from occupying all worker slots indefinitely.
- **Changed:** Frigate MQTT payloads are now pre-filtered before task scheduling, so non-actionable update chatter no longer consumes in-flight queue capacity.
- **Changed:** MQTT queue-pressure diagnostics now emit explicit saturation warnings (in-flight count + wait duration), making ingestion bottlenecks visible in backend logs instead of appearing silent.
- **Fixed:** Detection backfill now wraps per-event processing in a timeout guard, preventing a single slow/hung historical event from stalling the entire async backfill job indefinitely.
- **Fixed:** `ClassifierService` now uses separate thread pools for snapshot (`classify_async`) and video (`classify_video_async`) inference, preventing heavy background video analysis from starving real-time MQTT event classification.
- **Fixed:** Snapshot image inference now uses bounded admission control before executor dispatch; when workers are saturated, requests fail fast instead of piling up behind stuck/slow classifications.
- **Added:** MQTT service now exposes pressure telemetry (`pressure_level`, in-flight utilization, and threshold-based `under_pressure`) for diagnostics and adaptive scheduling.
- **Changed:** Auto video-classification queue now adaptively throttles effective concurrency when MQTT ingest pressure rises, prioritizing live `new/end` event processing during bursts.
- **Changed:** Detection backfill now uses a dedicated low-priority image inference executor so backfill classification no longer competes directly with live MQTT snapshot inference workers.
- **Changed:** `/health` now includes MQTT and video-classifier queue-pressure snapshots and marks health as `degraded` when MQTT pressure is high/critical.
- **Added:** New bounded async notification dispatcher service with configurable worker count, queue size, per-job timeout, and dropped-job accounting (`backend/app/services/notification_dispatcher.py`).
- **Changed:** Event ingestion now queues notification orchestration work instead of awaiting remote notification I/O inline, so notification slowness no longer blocks Frigate/BirdNET event processing.
- **Changed:** Notification queue saturation now fails safe by dropping excess notification jobs (with explicit warning logs and counters) rather than spawning unbounded fallback tasks in the ingest path.
- **Added:** MQTT topic-liveness watchdog for Frigate/BirdNET traffic asymmetry, including automatic MQTT session recycle when Frigate topic activity stalls while BirdNET remains active.
- **Added:** MQTT status telemetry now includes per-topic message counters, message-age metrics, connection uptime, liveness reconnect count, and last reconnect reason.
- **Changed:** `/health` now includes `notification_dispatcher` status and reports `degraded` when notification jobs have been dropped, surfacing notifier backpressure explicitly.
- **Added:** Backend regression tests covering queued notification dispatch, MQTT topic-stall reconnect detection, health degradation on notification drops, and MQTT-pressure throttling behavior for auto video classification.

- **Changed:** Clicking the bell notification icon now navigates directly to the full Notifications page instead of opening a dropdown menu.
- **Added:** A global progress bar now appears at the top of the application when background jobs (like backfills or batch analysis) are running, providing system-wide visibility into ongoing processes.
- **Changed:** Updated the global progress bar styling to match the emerald gradient theme used in the Notifications view.
- **Fixed:** Global progress aggregate calculations now sanitize and clamp malformed progress metadata, preventing invalid percentages or overflowed progress widths.
- **Changed:** Global progress multi-job summary text is now localized across supported UI languages instead of hard-coded English.
- **Fixed:** Global progress expand/collapse control now uses native button semantics with `aria-expanded`/`aria-controls` for better keyboard and screen-reader accessibility.

- **Fixed:** Dashboard Discovery Feed now correctly displays an empty state instead of continuous loading skeletons when there are no recent detections in the past 3 days.

- **Added:** Explorer filter toggle to show only detections with an "Audio Match".
- **Added:** Frigate logo asset for third-party integration representation (via acceptable use policy).
- **Changed:** Leaderboard and analytical statistics now group species queries using resilient canonical identities (`taxa_id` and `scientific_name`), making the UI immune to language switching and speeding up analytical database paths.
- **Added:** Single-image ONNX acceleration provider selector (`auto`, CPU, NVIDIA CUDA, Intel OpenVINO CPU/GPU) with runtime fallback reporting and Intel GPU auto-detection in the Settings UI.
- **Added:** Expanded classifier/OpenVINO diagnostics in Detection Settings and `/api/classifier/status` (OpenVINO version/import path, `/dev/dri` visibility, process UID/GID/groups, device list, and GPU probe errors) to make Intel iGPU setup failures debuggable in-container.
- **Added:** New non-interactive, movement-first video-analysis progress visualization for reclassification overlays (bottom thumbnail strip that advances with real analysis progress and scales to configurable frame counts), with a blurred current-frame/snapshot backdrop for clearer visual context.
- **Added:** `backend/scripts/patch_convnext_openvino_model.py` utility to patch `convnext_large_inat21` ONNX exports that fail OpenVINO compile with unsupported sequence ops (`SequenceEmpty`, `SequenceInsert`, `ConcatFromSequence`), with backup-on-replace behavior for in-place model remediation.
- **Added:** Personalization feedback persistence (`classification_feedback`) and manual-tag feedback capture during species corrections, including camera name, model ID, predicted label, corrected label, and original score.
- **Added:** Optional Personalized Re-ranking setting in Detection Settings, plus per-camera/per-model readiness diagnostics in `/api/classifier/status` and Detection Settings.
- **Changed:** Reclassification overlay progress presentation refined: larger bottom progress strip, centered progress/result stack, and a visible 30-second auto-close countdown after completion.
- **Changed:** Reclassification overlays now surface an `Auto Video` source badge for automatic video reclassification jobs (including the Analyze Unknowns pipeline), making batch/background runs distinguishable from manual reclassify actions.
- **Changed:** Detection Settings now surfaces ONNX inference provider/GPU acceleration controls in a dedicated panel (with an in-UI link to the repo GPU setup/diagnostics guide), and the bird naming style preference has been moved to Appearance Settings.
- **Changed:** Camera-aware inference paths now pass camera context into snapshot/video classification so personalized re-ranking can be applied consistently in live processing and manual/background reclassification flows.
- **Added:** AI Models settings cards now display model runtime and supported inference providers (CPU, NVIDIA CUDA, Intel OpenVINO CPU/GPU) so users can see which installed models can use each acceleration path.
- **Changed:** Active model cards now show only host-verified dynamic acceleration pills (CPU/CUDA/OpenVINO) and no longer duplicate static capability labels.
- **Fixed:** Added missing `ai_pricing_json` field to the backend settings update schema, resolving an issue where custom AI pricing inputs were not saved and reset to `[]`.
- **Fixed:** Corrected the AI Cost Estimation Reference link in the AI Settings UI to properly point to the reference documentation hosted on the project's GitHub repository.
- **Fixed:** CUDA availability detection now requires both the ONNX Runtime CUDA provider and a real NVIDIA CUDA device, preventing false-positive "CUDA available" status on Intel-only hosts.
- **Fixed:** OpenVINO runtime import compatibility now supports both legacy `openvino.runtime.Core` and OpenVINO 2026+ `openvino.Core`.
- **Fixed:** OpenVINO capability probing no longer risks backend startup crashes on unstable GPU plugin/driver combinations; GPU and device probes now run in isolated subprocesses and report diagnostics instead of crashing the API process.
- **Fixed:** Backend image now bundles Intel GPU userspace runtime dependencies (OpenCL + Level Zero via Intel graphics repo) for OpenVINO Intel iGPU support, and sets writable XDG cache/config paths to avoid OpenVINO telemetry/shader-cache warnings under non-root container users.
- **Fixed:** Detection Details now replaces the left media/video slot with the video-analysis progress UI during active analysis (`pending`/`processing`) instead of rendering a duplicate progress banner above the details panel.
- **Fixed:** Detection Details no longer shows the underlying video play button while the reclassification overlay is active.
- **Fixed:** Personalized re-ranking is fail-open with bounded score shifts; if feedback data is unavailable or errors occur, YA-WAMF falls back to base classifier scores.
- **Changed:** Updated the application icon set (including PWA assets, Apple Touch icon, and favicon) across the UI with a newly generated high-quality source image.
- **Fixed:** Explorer event-card weather summaries now use a two-tier layout with wrapping secondary metrics to prevent overflow in precipitation-heavy cases, and no longer duplicate temperature when freezing conditions are shown.
- **Changed:** Explorer event-card weather summaries now visually separate the primary weather summary from secondary weather details with labeled sub-rows for clearer hierarchy.
- **Changed:** Explorer event-card top weather row now shows only a generalized condition + temperature (with precipitation amounts/details kept in the Details row), and inner weather sub-panels use tighter horizontal padding.
- **Changed:** Explorer event-card top weather summary row no longer repeats a "Weather" label/icon header, reducing visual noise while preserving the labeled Details row.
- **Changed:** Explorer event-card weather sub-panels now use identical inner padding so summary/details cards align uniformly.
- **Fixed:** "Process Unknown Birds" now includes detections that are still labeled `Unknown Bird` even if a previous video classification run completed, allowing manual batch retries after model/config changes.
- **Fixed:** Explorer event cards now stay in sync more reliably during batch reclassification bursts; live updates no longer depend solely on the capped recent-detections list, and completed reclassifications trigger a debounced list refresh fallback to prevent stale `Unknown Bird` cards.
- **Changed:** Explorer pagination controls are now available at both the top and bottom of the event list to reduce extra scrolling during page-by-page review.
- **Changed:** Explorer now includes a manual "Refresh options" control for species/camera filters, and the page triggers a debounced metadata refresh after reclassification completions so newly introduced species appear in filter dropdowns without a full page reload.
- **Added:** `/api/events/filters` now supports `force_refresh=true` to bypass the short-lived filter-options cache when clients need immediate freshness.
- **Fixed:** BirdNET camera-audio mapping matching is now more resilient in correlation paths: comparisons are normalized for whitespace/case and accept legacy source IDs from raw payload metadata, reducing false mismatches after `nm` migration or mixed payload formats.
- **Added:** BirdNET camera-audio mappings now support multiple source names per camera (comma-separated), allowing multi-stream camera setups to correlate audio across multiple BirdNET sources.
- **Changed:** Detection cards and detection modal audio badges now show `No Audio Match` when audio does not confirm the visual species, and display nearby heard species instead of the previous generic `Heard` wording.
- **Added:** Events API now includes `audio_context_species` for unmatched-audio detections so cards can surface nearby BirdNET species without per-card fetches.
- **Fixed:** Manual-tag species options now hydrate missing taxonomy metadata on demand, improving common/scientific name coverage in locale-aware species pickers without requiring a full reload.
- **Fixed:** Active model capability pills now wrap cleanly on small/mobile cards to prevent overflow and clipped labels.
- **Fixed:** Dashboard "Recent Visitors" click-through now prefers stable `taxa:<id>` filters and no longer forces `date=today`, avoiding false "No events" results when sightings fall outside the local-day window.
- **Changed:** OpenVINO version pin raised from `>=2025.0.0,<2026.0` to `>=2025.4.0,<2026.0`. The 2025.4 release introduced a confirmed LayerNorm scale/bias reshape fix required for correct ViT-based model inference on Intel iGPU; 2026.0.0 is excluded because EVA-02 triggers a fatal `clWaitForEvents -14` process crash under that runtime, and 2026.0.1 is not available on PyPI.
- **Fixed:** Preprocessing registry metadata corrected for `small_birds` and `medium_birds` North America variants: both use `direct_resize` (not `center_crop`) with bilinear interpolation and no `crop_pct`, matching the actual `model_config.json` shipped with those artifacts. The `small_birds` Europe variant mean/std values have also been corrected to the CAPI/RoPE training statistics `[0.5248, 0.5372, 0.5086]` / `[0.2135, 0.2103, 0.2622]` (all values verified against released model config files).
- **Added:** OpenVINO GPU NaN fix probe test (`test_gpu_nan_fix_probe`) that runs every NaN-failing model through three recovery strategies — `HETERO:GPU,CPU`, SDPA-optimisation disabled, and both combined — and prints a comparison table. Results on this Intel iGPU with 2025.4.1: all three strategies still produce NaN for `rope_vit_b14_inat21` and `flexivit_il_all`; `hieradet_small_inat21` CPU inference is stable in isolation (the probe failure was a GPU-session-pollution artifact). No runtime fix is available for these models on this hardware without ONNX graph surgery.
- **Fixed:** `hieradet_small_inat21` registry `recommended_for` text removed an incorrect "Intel GPU" reference; the model is CPU and Intel CPU (OpenVINO) only.
- **Fixed:** `eva02_large_inat21` registry notes updated to confirm the fatal Intel GPU crash (`CL_OUT_OF_RESOURCES`) persists on OpenVINO 2025.4 — previously the note said "not retested on 2025.4."
- **Changed:** `eu_medium_focalnet_b` promoted to `GPU_VALIDATED` and `intel_gpu` added to its registry `supported_inference_providers`. With OpenVINO 2025.4.1 the model produces correct finite output (range ratio ≈1.0) in an isolated GPU context. Spearman correlation degrades when the GPU has been exercised by prior back-to-back model runs (a test-isolation artifact, not a production issue).
- **Fixed:** `eu_medium_focalnet_b` registry notes updated to reflect confirmed GPU support (was incorrectly marked "Intel GPU not supported"). GPU inference requires static-batch reshape (already applied by both the classifier service and the test harness).
- **Fixed:** `hieradet_dino_small_inat21` GPU_NOT_SUPPORTED failure reason corrected from "Compile error — HieraDeT architecture fails to load" to "NaN output — model compiles on GPU but produces non-finite values." The model uses standard `LayerNormalization` (fused to MVN by OpenVINO), so the NaN originates elsewhere — likely attention-scaling Sqrt ops or RoPE computations — and persists even after static-batch reshape.
- **Fixed:** `hieradet_dino_small_inat21` registry notes updated to match: "Intel GPU fails to compile" replaced with "Intel GPU produces non-finite outputs (NaN), confirmed on OpenVINO 2025.4."
- **Removed:** `hieradet_small_inat21` (ViT Reg4 M16 RMS Avg I-JEPA) and `hieradet_dino_small_inat21` (HieraDeT-D-Small + DINOv2) removed from the registry and GitHub release. Both are wildlife-wide small-tier models with confirmed GPU NaN and no unique niche — the wildlife-wide medium slot is covered by `rope_vit_b14_inat21` and large by `convnext_large_inat21`.
- **Kept:** `flexivit_il_all` (FlexiViT Global Birds) retained — unique global birds-only niche for users outside EU/NA (Asia, South America, Africa) with no dedicated regional model. CPU and Intel CPU validated.
- **Research:** Exhaustive ONNX graph surgery investigation for `hieradet_small_inat21` and `flexivit_il_all` GPU NaN. Root cause confirmed: Birder's custom RMSNorm decomposes to `Pow → ReduceMean(axes-as-tensor-input, opset 20) → Add(eps) → Sqrt → Reciprocal → Mul → Mul(scale)`. OpenVINO's MVN fusion pass pattern-matches only the standard `LayerNormalization` ONNX op; decomposed RMSNorm is not fused and produces NaN on GPU due to floating-point precision loss in the Sqrt chain. Approaches exhausted: (1) HETERO:GPU,CPU — NaN persists; (2) SDPA disabled — NaN persists; (3) ORT `SimplifiedLayerNormalization` fusion — OpenVINO rejects ORT custom ops; (4) Dynamo re-export at opset 20 — still decomposed; (5) Axes-to-attribute ONNX surgery at opset 17 — OpenVINO does not fuse the pattern even with attribute axes; (6) ONNX opset 23 `RMSNormalization` op — ORT 1.24.4 supports it but OpenVINO 2025.4 does not. Intel GPU support for these models requires either a future OpenVINO release that supports ONNX opset 23 `RMSNormalization`, or upstream Birder adoption of standard `LayerNormalization` export.
- **Added:** Comprehensive OpenVINO GPU diagnostic test suite (`backend/tests/test_model_openvino_gpu.py`) covering: ground-truth preprocessing validation against every installed `model_config.json`, NCHW float32 tensor shape/range checks, CPU-vs-GPU logit comparison (Spearman rank correlation ≥0.90, range ratio ≥0.5, top-5 overlap ≥1), a documented GPU support matrix with failure reasons for each known-unsupported model, and an always-passing diagnostic report test that prints a full comparison table across all installed models.

## [2.8.3] - 2026-02-23

- **Added:** New **AI Usage Dashboard** in Settings, providing real-time tracking of token consumption and estimated API costs for Gemini, OpenAI, and Claude.
- **Added:** Dynamic **AI Cost Estimation** with support for manual pricing overrides via a configurable JSON registry in the new AI tab.
- **Added:** **CUDA Acceleration** support for ONNX-based high-accuracy models (ConvNeXt, EVA-02) with a configurable UI toggle and real-time environment detection.
- **Added:** New **"AI" Settings Tab** to centralize LLM provider configuration, usage metrics, and prompt templates.
- **Added:** Configurable **Video Classification Frames** setting, allowing users to control the number of frames sampled for temporal ensemble analysis.
- **Added:** Refreshed **Application Icon Set** generated from a new high-quality source image.
- **Fixed:** Resolved species statistics grouping issues by prioritizing scientific name aggregation, ensuring accurate counts across different localized labels (e.g., Russian vs. English names).
- **Fixed:** Enhanced **Audio Correlation** to match against both scientific and common names, resolving "zero detection" issues when using localized BirdNet-Go instances.
- **Fixed:** Unified manual and background **Reclassification Logic** to ensure consistent display name updates and robust audio re-correlation.
- **Fixed:** Added `scientific_name` column to `audio_detections` table via a robust, idempotent migration following the Excellence Standard.
- **Fixed:** Resolved frontend build errors related to Svelte syntax in settings placeholders and missing interface properties.
- **Fixed:** Corrected backend test environment initialization so that Alembic migrations run automatically on temporary test databases, ensuring all tables are present during CI runs.
- **Changed:** Refactored AI usage logging to run as a non-blocking background task, improving API responsiveness.
- **Changed:** Fully localized all new UI elements and settings across all 9 supported languages.

## [2.8.2] - 2026-02-19

- **Fixed:** Detection-time email notifications now send reliably alongside Discord: corrected invalid Jinja in `bird_detection.html`, fixed snapshot fallback fetch handling, and added channel-level dispatch result logging so email skip/failure reasons are visible in backend logs.
- **Fixed:** Email notifications with "Only send on event end" now trigger on Frigate `end` events even when other channels already notified earlier in `standard`/`realtime`/`custom` modes; `silent` mode still suppresses all notifications.
- **Fixed:** Species enrichment matching is now more robust across languages for non-Wikipedia providers: iNaturalist taxon lookup now uses scored bird-only candidate selection (search + autocomplete + optional scientific-name hints), and eBird taxonomy matching now uses Unicode-safe normalization with locale resolution/fallback to avoid bad matches for localized names.
- **Fixed:** Species Wikipedia link resolution is now more robust across non-English locales (including Russian), using scored multilingual candidate selection plus scientific-name hints to avoid selecting similarly named but incorrect species pages.
- **Fixed:** Leaderboard species-info cache is now locale-aware, preventing stale cross-language external links/thumbnails after UI language switches.
- **Added:** Backend regression tests for multilingual Wikipedia article scoring and short-token boundary matching (`backend/tests/test_species_wikipedia_matching.py`).
- **Fixed:** Request middleware now handles client-disconnect cancellation paths gracefully, preventing noisy `RuntimeError: No response returned.` 500 traces during long-running calls such as event reclassification.
- **Fixed:** Detection modal manual-tag flow now provides explicit success/error toast feedback, sets pending state while saving, and hardens mobile interaction/scroll-lock behavior so species selection completes reliably and the picker closes cleanly after update.
- **Fixed:** Frigate `sub_label` values are now normalized when payloads arrive as arrays/objects, preventing SQLite binding crashes (`type 'list' is not supported`) during detection upserts/backfill/event processing.
- **Fixed:** Reclassification UI progress overlays now recover cleanly after failed requests; the backend emits a completion event on unexpected reclassification failures so clients do not remain stuck in pointer-blocking "in progress" state.
- **Fixed:** Date preset filtering in Events and initial detections loading now uses deterministic local-calendar `YYYY-MM-DD` formatting (via shared `toLocalYMD` utility) instead of UTC `toISOString()` splitting, preventing "today/week/month" drift around UTC day boundaries.

## [2.8.1] - 2026-02-14

- **Added:** Owner-curated favorite detections with idempotent API endpoints (`POST/DELETE /api/events/{event_id}/favorite`) and guest-safe read behavior.
- **Added:** Favorites filtering support on Events APIs (`favorites=true` on `/api/events` and `/api/events/count`) and Explorer UI toggle.
- **Changed:** Detection payloads now include `is_favorite` across list responses and SSE update flows so Dashboard/Explorer/Modal stay in sync.
- **Changed:** Retention cleanup now preserves favorited detections, and scheduled/manual media-cache cleanup now exempts favorite event media (snapshots, clips, previews).
- **Added:** Settings Data tab now includes an owner-only "Delete All Favorites" action with confirmation, API support, and localized UI copy across all supported languages.
- **Changed:** Email test-send flow now emits structured step-level SMTP/OAuth diagnostics (connect, STARTTLS, auth, send, timeout mode) to make delivery failures and timeouts debuggable from container logs.
- **Added:** New `detection_favorites` migration with guarded DDL, FK cascade semantics, and downgrade safety checks.
- **Fixed:** Resolved test-email template rendering error (`unexpected '\\'`) by correcting escaped quotes in the Jinja `font_family` default expression used by `POST /api/email/test`.
- **Changed:** Settings action feedback is now consistent across tabs: test/connect/disconnect/export actions route through unified status handling and toast notifications instead of mixed banner-only, inline-only, and `alert()` paths.
- **Fixed:** Settings dirty-state detection now includes `notifications_email_only_on_end` and `notifications_notification_cooldown_minutes`, so the unsaved-changes bar reliably appears for those edits.
- **Changed:** Secret handling in Settings is now consistent for redacted values (MQTT password, BirdWeather token, eBird key, iNaturalist credentials, LLM API key, and notification secrets) with unified “Saved” indicators and stable dirty-state behavior.
- **Changed:** Clarified Raspberry Pi support messaging in documentation; Pi compatibility is now explicitly described as best-effort ARM64 work in progress until physical-device validation is completed.
- **Added:** Roadmap now includes a detailed Raspberry Pi compatibility plan (multi-arch images, ARM dependency strategy, CI validation path, and real-hardware exit criteria).

## [2.8.0] - 2026-02-13

- **Fixed:** Owner system health notifications no longer reappear on every browser refresh when backend `/health` reports `status: ok`; stale health/cache system notices are now cleared when status is healthy.
- **Fixed:** Video player share-link manager now prevents mobile scroll bleed (background page scrolling behind the modal) and keeps long active-link lists scrollable within the overlay.
- **Changed:** About page was refactored for stronger accessibility and maintainability (semantic sections, in-page jump links, safer link rendering without `{@html}`, and translated About metadata keys across all supported locales).
- **Changed:** Documentation polish pass completed: README redundancy reduced, docs links standardized with icons, and docs index navigation made visually consistent.
- **Changed:** AI diagnostics clipboard controls now default to disabled (`localStorage` opt-in) and are only rendered when backend debug UI mode is enabled.
- **Added:** Public Access settings now include an optional "Share link base URL" used for generated video-share links in reverse-proxy/multi-domain deployments.
- **Changed:** Video share-link creation now uses the configured public share base URL when valid, with safe fallback to request host when unset/invalid.
- **Changed:** Locale key coverage pass completed across `de/es/fr/it/ja/pt/ru/zh` so frontend locale files now match English key coverage.
- **Fixed:** Hardened multiple Alembic migrations for SQLite-safe idempotency and downgrade reliability (guarded index/table drops, resilient recreation of missing indexes, and deterministic rollback of multilingual species cache rows).
- **Changed:** Documentation accuracy pass completed: API reference now reflects current route structure, setup/troubleshooting commands now use canonical compose service names, and Security-tab navigation wording is consistent across README/docs.
- **Added:** Docs CI guardrail (`backend/scripts/docs_consistency_check.py` + `docs-quality` workflow) to validate markdown links, detect stale doc terminology, and catch API endpoint drift in `docs/api.md`.

- **Fixed:** Leaderboard weather/toggle overlay updates now harden Apex options normalization (annotation bucket defaults + resilient y-axis series mapping) to prevent `Cannot read properties of undefined (reading 'push')` runtime crashes.
- **Fixed:** Apex chart update handling now catches both synchronous and async `updateOptions` failures and recreates the chart instance safely to avoid unhandled promise rejections.
- **Changed:** Dashboard/Species/Detections fetch failure logging now classifies transient network/abort errors and records them as warnings instead of noisy hard errors.
- **Fixed:** Mobile header action buttons now provide explicit/fallback accessible names, and key dashboard/list badges were adjusted for stronger light-mode contrast.

- **Added:** Leaderboard now includes two additional analytics panels beneath the main detections chart:
  - Species comparison trend chart for the top species in the selected window.
  - Activity heatmap chart (hour x weekday) for the selected window.
- **Added:** New stats API endpoint `GET /api/stats/detections/activity-heatmap` for 7x24 detection activity aggregation by weekday/hour.
- **Changed:** Leaderboard timeline loading now fetches compare-series data and heatmap data in parallel with graceful partial-failure handling.
- **Changed:** Added i18n keys/translations for new leaderboard analytics cards and weekday labels across supported locales.

- **Changed:** Removed the mobile-only Bottom Navigation bar to avoid duplicate navigation patterns with the existing mobile sidebar/menu.
- **Fixed:** Owner "system status" startup notifications are now emitted once per backend startup instance (using a startup instance marker), instead of being re-created on every page refresh.
- **Changed:** Leaderboard range controls now default to **Month** and are ordered **Month → Week → Day → All Time** for a more useful first view.
- **Changed:** Leaderboard chart header metadata was compacted into icon chips (range/grouping/metric) to reduce visual noise and long range strings.
- **Added:** Leaderboard chart now supports metric modes (`Detections`, `Unique species`, `Avg confidence`) plus trend modes (`Raw`, `Smooth`, `Both`).
- **Added:** Leaderboard chart now supports multi-species compare overlays (up to 3 species) and anomaly spike markers.
- **Added:** Timeline API now returns per-bucket `unique_species`, `avg_confidence`, and optional `compare_series` for selected species.
- **Fixed:** Safari dark-mode overscroll/root paint now consistently matches the active theme (including startup theme bootstrap) instead of flashing/lightening to white.
- **Changed:** Refined Leaderboard visual aesthetic with asymmetrical thumbnail overlaps for a bespoke "field journal" feel.
- **Changed:** Refined global color palette: deeper "Midnight" dark mode and warmer "Parchment" light mode for improved atmosphere and character.
- **Added:** Staggered entrance animations for Dashboard and Explorer cards to improve perceived performance and polish.
- **Fixed:** Standardized badge and chip styles across the UI for better visual consistency.
- **Fixed:** Video modal now includes a subtle zoom-in entrance transition and themed Plyr playback controls.
- **Fixed:** Leaderboard sunrise/sunset ranges now use local timezone data from weather APIs (instead of forced UTC), improving real-world day/week/month display accuracy.
- **Fixed:** Leaderboard sunrise/sunset range formatting now parses and sorts by clock-time values for stable ascending ranges (for example `07:28–08:13`).
- **Changed:** Leaderboard detections chart now defaults to histogram-style bars on Week/Month views while preserving line/area trend rendering for shorter ranges.
- **Changed:** Video modal mobile controls now use stronger contrast, larger touch targets, and explicit labels on preview/download actions for clearer visibility.
- **Changed:** Keyboard shortcuts modal is now grouped into clearer sections with improved key-description hierarchy.
- **Added:** Leaderboard chart-mode toggle (`Auto`, `Line`, `Histogram`) so users can override the default visualization mode per preference.
- **Changed:** Leaderboard chart subtitle/config metadata now include the active chart mode for clearer context and AI analysis consistency.
- **Added:** Backend regression tests for local-time sun fetch and sunrise/sunset range formatting behavior.
- **Fixed:** Detection modal mobile “Play video” interaction now uses a dedicated high-priority touch target and explicit event handling to avoid pointer interception.
- **Fixed:** Events/Dashboard video open flow now uses an explicit `videoEventId` handoff, closing detection details before opening the video modal to prevent modal-stacking race conditions.
- **Fixed:** Video autoplay startup no longer gets interrupted by timeline-preview attachment; preview activation is deferred until player startup settles.
- **Changed:** Timeline preview notifications now suppress transient `checking/deferred` noise and dedupe final state updates to avoid per-open notification spam.
- **Fixed:** Detection repository write-result checks now use per-statement SQLite `changes()` semantics (not cumulative `total_changes`), preventing false positives on pooled DB connections.
- **Fixed:** iNaturalist token deletion now returns accurate success/failure based on the last DELETE statement instead of cumulative connection write history.
- **Changed:** Notification delay-until-video flow now waits on an in-process video-classification completion signal, removing DB polling loops while preserving timeout fallback behavior.
- **Changed:** Video autoplay startup now accepts explicit user play intent and coordinates first playback with player readiness, with safer muted-first fallback for non-user-initiated starts.
- **Fixed:** Video modal playback-status chip no longer sticks on `Paused`; state now tracks the active media element even when player internals swap the underlying `<video>` node.
- **Fixed:** Timeline preview WebVTT cues now emit path-based sprite URLs instead of host-bound absolute URLs, so previews remain functional behind reverse proxies and non-default host headers.
- **Added:** E2E guard in `tests/e2e/test_video_player.py` to fail if playback is active while the status chip still renders the paused style.
- **Added:** Video modal now includes a dedicated share action that uses native share sheets when available and falls back to copying a deep link (`/events?event=<id>&video=1`) to clipboard.
- **Added:** Events page now supports video deep links via `?event=<frigate_event>&video=1`, opening the video modal directly.
- **Fixed:** Deferred timeline-preview activation now updates the active Plyr instance in place instead of recreating the player, preventing interaction-triggered fallback to native controls.
- **Added:** Events page now supports share-token deep links via `?event=<frigate_event>&video=1&share=<token>`, including direct modal open and token-aware playback URLs.
- **Added:** Owner-only expiring video-share API endpoints (`POST /api/video-share`, `GET /api/video-share/{event_id}`) backed by hashed tokens and expiry checks.
- **Added:** Owner share-link management APIs (`GET /api/video-share/{event_id}/links`, `PATCH /api/video-share/{event_id}/links/{link_id}`, `POST /api/video-share/{event_id}/links/{link_id}/revoke`) for active-link lifecycle control.
- **Changed:** Video-share creation now has explicit anti-abuse rate limits (`10/minute;60/hour`) and emits structured share-audit logs for create/update/revoke actions.
- **Changed:** Maintenance cleanup now purges expired/revoked video-share links on the scheduled cleanup cycle.
- **Added:** Video modal now includes an owner share-management panel to create links with TTL/watermark presets, list active links, and revoke/update links in place.
- **Added:** Backend proxy tests now cover share-link create/list/update/revoke endpoint behavior.
- **Added:** Shared video playback now renders a watermark label/expiry context in the modal and disables direct clip downloads for shared-link sessions.
- **Added:** Events now include a grouped day timeline strip with keyboard navigation (`[`, `]`, `0`) for faster time-based browsing.
- **Fixed:** Notification Center no longer emits noisy per-video "Timeline previews enabled" updates when opening clips.
- **Fixed:** Event processor error logging now captures event ID deterministically without `locals()` fallback hacks.
- **Changed:** CSP policy now removes `script-src 'unsafe-inline'` and adds `object-src 'none'`/`base-uri 'self'` hardening.
- **Changed:** Remaining hardcoded UI copy in key components (header/sidebar/video modal/toasts/top visitors/mobile shell) has been routed through i18n keys/defaults.

- **Added:** Video modal clip download action (`download=1`) with backend enforcement that allows owners always and guests only when explicitly enabled.
- **Added:** New public-access setting to control guest clip downloads (UI + API + auth status propagation): `public_access_allow_clip_downloads` / `PUBLIC_ACCESS__ALLOW_CLIP_DOWNLOADS`.
- **Changed:** Public-access settings now include an explicit “Allow clip downloads” toggle for guest users.
- **Changed:** Troubleshooting and setup docs now include step-by-step non-root permission remediation with exact `PUID`/`PGID`, compose snippets, and verification commands.
- **Changed:** Video playback UI migrated to Plyr for a more compact, familiar control surface with robust keyboard support and cleaner modal behavior.
- **Added:** Server-generated timeline preview thumbnails (sprite + WebVTT) via new media proxy endpoints:
  - `GET /api/frigate/{event_id}/clip-thumbnails.vtt`
  - `GET /api/frigate/{event_id}/clip-thumbnails.jpg`
- **Changed:** Timeline preview generation now uses the backend media-cache lifecycle (retention, orphan cleanup, empty-file cleanup, and cache stats integration).
- **Changed:** Timeline previews are now explicitly disabled when media cache is disabled (backend returns `503`; UI shows a clear disabled state).
- **Added:** Video modal now shows an indeterminate progress-bar notification while timeline previews are being checked/generated.
- **Added:** Prometheus metrics for timeline preview request outcomes and generation duration.
- **Changed:** Video player E2E coverage now validates Plyr controls, close button visibility, explicit preview-state messaging, and hover-preview rendering when preview tracks are available.
- **Fixed:** Video modal initialization watchdog no longer uses reactive timer state, preventing Svelte `effect_update_depth_exceeded` loops and full-UI hangs when opening playback.
- **Fixed:** Video player initialization now waits for the bound `<video>` element and uses bounded probe timeouts so modal startup cannot stall indefinitely on media probe requests.
- **Fixed:** Video player now initializes Plyr immediately after clip availability checks and probes preview thumbnails asynchronously, preventing controls from stalling while preview assets are generated.
- **Fixed:** Explorer and Leaderboard now surface backend load failures instead of silently rendering empty views, and leaderboard fetches the table and timeline independently (so one failing request does not blank the whole page).
- **Changed:** Release builds now derive `APP_VERSION` from the git tag and avoid embedding tag names as “branch” identifiers, preventing malformed version strings in telemetry and `/api/version`.
- **Changed:** Backend startup now logs explicit lifecycle phases with timing and marks non-fatal startup failures as `startup_warnings`.
- **Added:** New readiness endpoint `GET /ready` for orchestration health checks; returns `503` with details when startup is not ready.
- **Changed:** Health endpoint `GET /health` now includes `startup_warnings` and reports `degraded` when startup had non-fatal phase failures.
- **Changed:** Classifier/event-processor initialization is now deferred to runtime startup (not module import), improving startup failure attribution and resilience.
- **Fixed:** Leaderboard weather/temperature/wind/precip controls now remain visible even when overlay data is unavailable; controls are disabled with explicit hints (no weather data yet vs range limitation).
- **Added:** Video modal now includes hover timeline previews (sprite + WebVTT) when preview assets are available.
- **Changed:** Video modal now supports compact Plyr controls, keyboard seek/play shortcuts, and clearer preview-state messaging.
- **Changed:** Video modal bottom-bar now uses icon-only controls for preview status and clip download (with accessible labels/tooltips).
- **Fixed:** Video modal now attaches deferred timeline previews when playback pauses/ends instead of leaving preview state deferred indefinitely.
- **Added:** Timeline preview generation/availability now appears in Notification Center as process/update events for owner sessions.
- **Changed:** Video modal shortcut hint now uses compact keyboard/icon chips instead of plain text.
- **Fixed:** Video modal close button no longer overlays playback controls/content on mobile; close action is now in the modal header.
- **Changed:** Video modal bottom-bar chips and action icons now use larger touch targets and improved mobile spacing.
- **Fixed:** Video modal mobile action buttons (preview/download) now remain clearly visible with explicit labels and consistent icon sizing.
- **Changed:** Video modal keyboard shortcut hint now uses simpler text (mobile-friendly) instead of dense icon chips.
- **Changed:** Video modal now shows a touch-device-only timeline preview hint when previews are enabled, clarifying scrub behavior on mobile.
- **Changed:** Notification Center now includes source metadata, supports click-through deep links to relevant pages, and uses stronger dedupe/throttle logic for noisy SSE-driven updates.
- **Added:** Notification lifecycle hardening for owner sessions: stale in-progress items are auto-settled, SSE disconnect warnings are surfaced, and startup health/media-cache checks can raise actionable system notifications.
- **Changed:** Events page now supports `?event=<frigate_event>` deep links, allowing notification click-through to open the matching detection modal when present in the current result set.
- **Added:** Settings updates now broadcast a `settings_updated` SSE event so owner sessions receive real-time notification updates after configuration changes.
- **Changed:** Backend startup/shutdown CI smoke test now verifies `/health` and `/ready` responses under real lifespan startup.
- **Changed:** CI now runs a sampled Alembic upgrade-path matrix (multiple historical revisions → head), with SQLite integrity/FK checks and app-level `init_db()` validation on each path.

## [2.7.9] - 2026-02-08

- **Fixed:** Detection modal “Frame Grid” (reclassification/video analysis overlay) now scrolls so action buttons aren’t cut off on smaller viewports.
- **Fixed:** Settings “Send Test Notification” now calls Telegram and Pushover notification helpers with the correct argument order (prevents Telegram confidence parsing crash).
- **Changed:** Email notifications now use the configured UI font theme for their HTML templates (email clients may fall back to system fonts).
- **Changed:** Overscroll background and PWA/mobile browser chrome (`theme-color`) now track the active theme (light/dark/high-contrast).
- **Fixed:** Settings route now prompts for login and blocks rendering for unauthenticated users when Public Access is enabled (prevents guests directly navigating to `/settings` and generating noisy 403s).
- **Fixed:** Leaderboard ranking now defaults to **Total** (all-time), and “Unknown Bird” can be toggled on/off from the leaderboard table.
- **Fixed:** Leaderboard “Detections over time” chart now reacts to the Day/Week/Month selection (bucketed timeline), and shows an explicit range/grouping label (with optional weather overlays when location data is available).
- **Fixed:** Leaderboard chart weather-unit labels and species summary source attribution labels are now localized.
- **Fixed:** Leaderboard “All Species” summary now shows explicit date ranges for the 7-day and 30-day totals.
- **Fixed:** Traditional SMTP email now uses STARTTLS on port 587 when “TLS/STARTTLS” is enabled (and implicit TLS on 465).
- **Fixed:** Telegram notifications now truncate long bodies to respect Telegram length limits, and disable link previews in the text-only path.
- **Changed:** Email OAuth (Gmail/Outlook) connect/refresh logic hardened for SMTP XOAUTH2 flows (still needs end-to-end testing).
- **Changed:** Renamed the font picker “Default” label to “Modern” (Classic remains the actual default).
- **Changed:** Added `INTEGRATION_TESTING.md` and moved `ISSUES.md` to the repo root to make untested integrations and testing requests easier to find.
- **Fixed:** Home Assistant integration options flow no longer crashes on newer Home Assistant versions (prevents “Config flow could not be loaded: 500”).
- **Security:** Removed hardcoded MQTT credentials from a debugging script.
- **Changed:** Marked Email OAuth (Gmail/Outlook), Telegram Bot API, and iNaturalist submission flows as “needs testing” in `ISSUES.md`.

## [2.7.8] - 2026-02-07

- **Changed:** Default AI analysis and conversation prompt templates now prefer short paragraphs (instead of bullet-only formatting) for a more natural “field note” style.
- **Fixed:** PWA service worker updates now auto-apply; the “Update available” toast no longer appears on every refresh.
- **Fixed:** Backend tests no longer hang in this environment by replacing FastAPI `TestClient` usage with direct ASGI (`httpx.ASGITransport`) clients.
- **Fixed:** Regenerating AI analysis now clears the persisted AI conversation history for that detection (and the UI warns about this behavior).
- **Changed:** Hardened multiple Alembic migrations to be SQLite-safe and idempotent (guarded table/index/column operations and safer downgrades).
- **Changed:** AI surfaces in Detection Details modal refined in dark mode for a less stark, more cohesive look.

## [2.7.7] - 2026-02-07

- **Added:** AI conversation threads per detection with persisted history.
- **Added:** PWA service worker for offline caching and installability.
- **Added:** PWA update notifications and refresh prompt.
- **Added:** LLM connection test endpoint and Settings UI action for validating API keys.
- **Added:** Telemetry transparency details in Settings (installation ID, platform, flags, frequency).
- **Changed:** EventProcessor notification flow decomposed into a dedicated orchestrator.
- **Added:** Composite index on detections (`camera_name`, `detection_time`) for faster queries.
- **Changed:** AI analysis rendering now uses a cleaner markdown layout and improved dark-mode contrast.
- **Changed:** Settings panels now align cards to consistent heights and widths.
- **Changed:** Settings tooltips and aria-labels are fully localized.
- **Changed:** Default font theme is now Classic.
- **Fixed:** AI analysis text now renders brighter in dark mode and avoids over-eager list formatting.
- **Fixed:** Detection modal AI analysis panel now boosts dark-mode contrast for headings, body text, and code blocks.
- **Fixed:** Notification settings cards now size per row instead of matching the tallest card on the page.
- **Fixed:** Integration and authentication settings cards now size per row instead of matching the tallest card on the page.
- **Fixed:** AI analysis markdown now correctly applies dark-mode text colors for injected content.
- **Changed:** AI analysis markdown now promotes uppercase section lines to headings and restores dark-mode input contrast for follow-up questions.
- **Changed:** AI markdown now uses a unified Markdown parser, and prompt templates are configurable from Settings → Debug.
- **Added:** Localized prompt templates with selectable styles and a reset option in Settings → Debug.
- **Fixed:** CI errors by adding markdown-it typings and associating prompt editor labels with inputs.
- **Fixed:** Normalized AI markdown formatting for headings and bullet lists across analysis and conversation views.
- **Changed:** Unified AI analysis and conversation surfaces for consistent typography and contrast in light/dark modes.
- **Fixed:** Detection modal AI text now uses bright dark-mode colors and tighter heading/paragraph spacing.
- **Changed:** Expanded AI markdown styling coverage (lists, quotes, code blocks, tables, links) for light/dark modes.
- **Fixed:** AI conversation markdown now inherits panel colors correctly in dark mode and uses tighter heading/list spacing.
- **Changed:** Security reporting now accepts public GitHub issues for vulnerability reports.
- **Added:** Debug-only AI diagnostics panel in the detection modal for collecting markdown/theme contrast details.
- **Fixed:** AI markdown dark-mode styles now apply even when the modal is outside the global `.dark` tree.
- **Added:** AI diagnostics panel now supports copying raw AI content and prompt templates.
- **Added:** AI diagnostics panel can copy a full diagnostics bundle in one click.
- **Changed:** AI markdown styling now uses a dedicated surface class for stronger specificity in all themes.
- **Added:** Debug setting to toggle the AI diagnostics clipboard button on detection modals.

## [2.7.6] - 2026-02-06

- **Added:** First-run language picker with persisted preference.
- **Changed:** First-run setup, telemetry banner, and eBird sections in detection/species modals now use i18n keys.
- **Changed:** Settings tab labels fully localized (including Enrichment).

## [2.7.5] - 2026-02-04

- **Fixed:** Authenticated media (snapshots/clips/thumbnails) now include query tokens so owner access is honored even when public access limits are enabled.
- **Added:** Public access settings now include a separate media history window (snapshots/clips) from the detections list.
- **Fixed:** eBird nearby sightings now render even when species code resolution fails (warning no longer suppresses results).
- **Added:** Configurable date formats (US/UK/JP-CN) with consistent formatting across the UI.
- **Added:** Detection details now display the detection/event ID.
- **Added:** Range map zoom controls in the species detail view.
- **Changed:** Range map panel grows taller when eBird is disabled.
- **Fixed:** Species cards now respect enrichment summary/seasonality settings and avoid fetching disabled sources.
- **Fixed:** Species card labels and empty summary messaging now use localized translations.
- **Changed:** Enrichment sources are now automatic: eBird API key enables eBird-first enrichment with iNaturalist seasonality fallback; without a key, Wikipedia + iNaturalist are used.
- **Changed:** Enrichment settings UI is now read-only and reflects the effective source selection.
- **Fixed:** Added missing seasonality labels for species detail translations across locales.
- **Added:** Species detail modal now includes a GBIF-based global range map under seasonality.
- **Fixed:** Detection details now distinguish between confirmed audio matches and merely detected audio.
- **Fixed:** Detection cards and hero badge now distinguish audio detected vs confirmed.
- **Changed:** Range map now defaults to a wider zoom and includes interaction hints.
- **Fixed:** eBird usage now respects the integration toggle; disabled eBird no longer drives enrichments.
- **Changed:** Species detail activity charts now match the modal card styling for a more consistent look.
- **Changed:** Refined UI cohesion with unified navigation, button, and form-control styling.
- **Changed:** Refined Species Detail modal styling for consistent cards, headers, and recent sightings layout.
- **Changed:** Events species filter now uses taxonomic normalization and respects naming preferences.
- **Added:** Data settings now include cleanup actions for detections missing clips or snapshots.
- **Added:** Detection cards now show classification source (manual, video, snapshot).
- **Changed:** Media purge endpoints guard against Frigate outages and disabled clips.
- **Added:** Events page now includes a legend for classification source badges.
- **Changed:** eBird integration docs now recommend enabling eBird and clarify enrichment behavior.
- **Added:** Appearance settings now include a font switcher with multiple typography presets.
- **Fixed:** Mobile navigation now always uses the vertical layout for reliable menu access.
- **Changed:** Appearance settings now clarify that font changes apply immediately.
- **Fixed:** Font switcher now consistently applies across the UI.
- **Added:** Appearance settings now show language coverage hints for each font preset.

## [2.7.4] - 2026-02-03

- **Added:** eBird integration as a primary enrichment source for Species Info and Taxonomy (Common Names).
- **Changed:** Taxonomy lookup now respects the configured "Taxonomy Source" in settings. If set to eBird, the system prefers eBird common names (e.g., "Eurasian Blackbird") while still maintaining iNaturalist links for seasonality data.
- **Fixed:** eBird CSV export now fully complies with the "eBird Record Format (Extended)" specification (19 columns), ensuring successful imports without "Unknown species" or "Invalid date" errors.
- **Fixed:** eBird CSV export now uses the database's normalized `common_name`, resolving import mismatches (e.g., matching "Turdus merula" to "Eurasian Blackbird").
- **Changed:** UI Enrichment Settings now include eBird as a valid source for Summary and Taxonomy.
- **Changed:** Source attribution pills in detection details now always reflect the actual source of the displayed information.
- **Fixed:** Added a fallback note in Enrichment Settings to clarify that eBird taxonomy falls back to iNaturalist for missing IDs.

## [2.7.3] - 2026-02-03

- **Fixed:** Restored `taxa_id` lookup flow to ensure seasonality and localized names load when taxonomy cache entries exist or recent detections provide the ID.
- **Fixed:** Filled missing Detection settings translation keys across all supported locales.
- **Fixed:** Localized retention duration labels instead of relying on hardcoded language checks.
- **Fixed:** Added a generic localized fallback for test email failures.
- **Fixed:** Resolved eBird API 400 error caused by invalid `genus` category and added backend error handling for eBird service failures.
- **Fixed:** Expanded Wikipedia bird validation to support higher taxonomic ranks (Family, Genus, Order) and multiple languages (DE, FR, ES, IT, NL, PT, PL, RU).
- **Fixed:** Improved UI error states for eBird sightings in species and detection modals.
- **Fixed:** Aligned eBird CSV export with the standard 16-column Record Format (Extended) and removed the header row to prevent import parsing errors.

## [2.7.2] - 2026-02-03

- **Fixed:** Resolved issue where enrichments (eBird sightings, iNaturalist seasonality) were hidden in guest mode due to missing configuration state and restricted endpoints.
- **Added:** Public configuration state is now synchronized to guests via the auth status endpoint, enabling correct localized naming and feature toggles without requiring owner login.
- **Changed:** eBird taxonomic lookups now include Genus, Spuh, Slash, and ISSF categories, enabling lookups for broader groups like "Siskins and New World Goldfinches" (genus `Spinus`).
- **Changed:** eBird resolution now automatically falls back to scientific names if common name lookups fail.
- **Fixed:** Resolved issue where Seasonality chart would not appear in modals due to missing `taxa_id` in some API responses.
- **Added:** Comprehensive translation sync across all 9 supported languages, ensuring all settings panels (Data, Integrations, Enrichment) are fully localized.
- **Fixed:** Corrected multiple TypeScript and syntax issues in the frontend, resulting in a clean `npm run check`.
- **Fixed:** Accessibility live announcements now respect user settings even in guest mode.
- **Fixed:** Resolved JSON syntax error in German locale file (`de.json`).
- **Fixed:** Added missing `AuthStatusResponse` type handling in frontend API service.

## [2.7.1] - 2026-02-02

- **Added:** New dedicated Enrichment tab in Settings for centralizing all species data source configurations.
- **Added:** Interactive Map visualization for eBird sightings in species and detection modals (user location hidden in guest mode).
- **Changed:** Map visualization in guest mode now centers on a random sighting rather than the geometric center to prevent location inference.
- **Added:** eBird Notable Nearby sightings now include species thumbnails powered by iNaturalist.
- **Added:** Local Seasonality chart in Species Details (replacing Notable Nearby), showing monthly observation frequency from iNaturalist.
- **Changed:** Dashboard "Top Visitor" stat card now has a cleaner layout without the numeric visit count.
- **Fixed:** Resolved issue where Seasonality chart would appear blank due to missing taxonomy ID.
- **Added:** Expanded telemetry collection to include feature usage (notifications, integrations, enrichment settings) for better development insights.
- **Changed:** Refined Species Info, Recent Sightings, and Notable Nearby sections in Detection and Species modals with a new structured "beautiful" card-based layout.
- **Fixed:** Resolved mobile scrollability issue in the Detection Details pane.
- **Fixed:** Critical iNaturalist token expiration bug by implementing automatic refresh logic.
- **Fixed:** Multiple TypeScript and accessibility issues across frontend components, resulting in a clean build check.
- **Added:** Visual headers and icons for all enrichment sources (Wikipedia, eBird, iNaturalist) in modals.
- **Changed:** Centralized enrichment provider selection logic to ensure consistent data presentation across the UI.

## [2.7.0] - 2026-02-01

- **Added:** Notification Center now separates ongoing actions with pinned progress bars for long-running jobs.
- **Added:** Notification Center expand button opens a full notifications page.
- **Added:** Camera selection now includes a snapshot preview in Connection settings (auto-refreshing).
- **Fixed:** iNaturalist settings now correctly mark the Settings page dirty so changes can be saved.
- **Fixed:** Common "Show/Hide" labels now translate correctly in detection detail expanders.
- **Fixed:** Background tasks now log unhandled exceptions instead of failing silently.
- **Added:** Global exception handler now logs unhandled 500s with structured context.
- **Fixed:** Camera preview now uses a backend proxy (avoids CSP/mixed-content issues and supports auth).
- **Changed:** Database reset now pauses ingestion and cancels long-running jobs for a clean slate.
- **Fixed:** Notification Center popout aligns correctly in horizontal navigation and uses stronger shadows.
- **Changed:** Camera preview is now an accordion toggle (mobile-friendly, no popout clipping).
- **Fixed:** Camera preview works with unauthenticated Frigate endpoints and owner-auth mode.
- **Fixed:** Settings updates no longer overwrite unrelated fields on partial updates.
- **Added:** Auto video classification queue now has a safety cap with cleanup to prevent unbounded growth.
- **Changed:** EventProcessor flow refactored for clearer, more robust handling.
- **Added:** Leaderboard chart AI analysis with persisted insights and rerun support.
- **Changed:** AI analysis responses now respect the configured UI language.
- **Changed:** Leaderboard AI analysis always includes all weather overlays for richer insights.
- **Changed:** Leaderboard AI analysis now includes sunrise/sunset ranges in the prompt and chart capture.
- **Fixed:** Leaderboard chart analysis now correctly passes PNG mime types for Claude.
- **Fixed:** ApexCharts subtitle no longer throws errors when analysis banners toggle.
- **Changed:** Added render delays to ensure all chart overlays are captured before AI analysis.
- **Fixed:** Camera list now fills the available height in Connection settings.

## [2.6.8] - 2026-01-31

- **Changed:** Dashboard summary stats now use a rolling last-24-hours window for detections, species, top visitor, and audio confirmations.
- **Added:** Top Visitor stat now uses species thumbnail imagery (iNaturalist/Wikipedia) when available.
- **Changed:** Detection cards now show compact weather icons; audio context and detailed weather expanders now live in the detection details panel.
- **Changed:** Audio badges now only show when audio confirms the visual detection.
- **Added:** Audio detections are now persisted in the database so audio context survives in-memory buffer expiry.
- **Added:** Detection details now include expandable weather summaries (wind, cloud cover, precipitation).
- **Added:** Weather backfill action in Settings → Data to populate missing weather fields for historical detections.
- **Added:** Detections over time chart now shows subtle AM/PM rain/snow bands per day with a small legend, plus a temperature line series.
- **Added:** Detections over time chart now supports toggling weather bands/temperature/wind, shows average wind speed, and displays sunrise/sunset ranges.
- **Added:** Detections over time chart now supports a precipitation toggle with mm values.
- **Changed:** Adjusted precipitation chart styling and removed the native chart legend to use the custom legend.
- **Fixed:** Unknown Bird modal now correctly loads aggregated stats even when the underlying label is background/unknown.
- **Fixed:** Species detail modal close buttons now use explicit click handlers to avoid stuck modals.
- **Added:** Backfill jobs now run in the background with progress tracking so you can navigate away and return safely.
- **Added:** iNaturalist submission panel can be previewed without OAuth by enabling preview mode.
- **Fixed:** Test email failures now surface readable error feedback instead of an unhandled promise rejection.
- **Fixed:** Unknown Bird species modal now shows reclassification actions and a link to review detections in Explorer instead of a blank panel.
- **Changed:** Notifications now require a confirmed snapshot (confidence threshold or audio-confirmed) or confirmed video result before sending.
- **Fixed:** Email notifications now include Date/Message-ID headers and toned-down HTML sizing to reduce spam flags.
- **Added:** iNaturalist submission integration (owner-reviewed), with OAuth settings UI, connection flow, and detection-detail submission panel.
- **Added:** iNaturalist integration documentation and About page feature entry (marked untested pending App Owner credentials).
- **Fixed:** Leaderboard weather overlay removed wind/cloud bands; temperature plotted alongside detections for clarity.
- **Added:** Notification Center bell with persistent detection, reclassification, and backfill status updates.
- **Added:** Backfill async runs now broadcast start/progress/completion events for real-time UI updates.
- **Fixed:** Settings updates no longer overwrite existing secrets when placeholders or empty values are sent.
- **Changed:** Telegram notifications now use HTML escaping to prevent Markdown injection.
- **Changed:** Notification status icon now uses a chat bubble to avoid confusion with the Notification Center bell.
- **Added:** Reclassification progress now updates a pinned notification while batch analysis runs.
- **Changed:** Notifications settings now use a mode selector (Final-only / Standard / Realtime / Silent) with advanced overrides.
- **Added:** Notification mode is now stored in settings and respected by the backend dispatcher.
- **Added:** Optional Debug tab in Settings (gated by config) with iNaturalist preview toggle.

## [2.6.7] - 2026-01-29

- **Fixed:** Refined Audio/Video correlation logic: Audio detections can no longer "upgrade" the species name of a visual detection. Audio is now strictly for verification and metadata ("also heard").
- **Fixed:** High-confidence Video Analysis results now intelligently override the primary species identification and score if they provide a better match than the initial snapshot.
- **Fixed:** Automated re-evaluation of audio confirmation badges when video analysis corrects or updates a species identification.
- **Added:** Application versioning now includes the current git branch name (e.g., `2.6.7-dev+abc1234`) across the UI, Backend, and Telemetry.
- **Added:** Nginx Reverse Proxy guide updated with dynamic DNS resolution (resolver) to prevent "System Offline" (502) errors when container IPs change.
- **Changed:** Removed all references to the defunct generic wildlife classifier from documentation, the About page, and architectural diagrams.
- **Changed:** Standardized project documentation tone to use first-person singular ("I/me/my") throughout all Markdown files.
- **Fixed:** Resolved "System Offline" errors caused by stale DNS cache in Nginx Proxy Manager.
- **Fixed:** Resolved multiple TypeScript and Svelte compilation errors across settings components.
- **Fixed:** Corrected i18n interpolation usage and aria-label type mismatches in UI components.
- **Fixed:** Improved `onMount` async handling in `App.svelte` to prevent type mismatches.
- **Fixed:** Updated `Settings` interface to include missing notification and cooldown properties.
- **Added:** New `Reverse Proxy Configuration Guide` with detailed Cloudflare Tunnel and Nginx Proxy Manager examples.
- **Added:** Standardized trusted proxy configuration to automatically support RFC1918 private subnets (Docker/K8s) by default.
- **Added:** Module declaration for `svelte-apexcharts` to fix missing type definitions.
- **Fixed:** Enforced guest access checks for Frigate media proxies to prevent access to hidden or out-of-range events.
- **Fixed:** Added guest rate limiting to classifier status/label endpoints.
- **Fixed:** Added security headers to frontend Nginx responses.
- **Fixed:** Updated CSP to allow Cloudflare Insights script and beacon endpoints.
- **Fixed:** Allowed external image hosts in frontend CSP to prevent leaderboard thumbnail blocking.
- **Changed:** Disabled frontend production sourcemaps by default.
- **Fixed:** Added FastAPI request args to rate-limited classifier endpoints to satisfy SlowAPI.
- **Fixed:** Allowed media proxy access checks to fall back gracefully when the detections table is unavailable (test DB).
- **Changed:** Updated language utility tests to recognize Portuguese as supported.
- **Added:** Portuguese, Russian, and Italian UI translations.
- **Added:** Playwright-based console capture and Lighthouse runner scripts for external audits.
- **Added:** Leaderboard image inspection script for troubleshooting missing thumbnails.
- **Fixed:** Mark stale video analysis tasks as failed and added a timeout to prevent indefinite "in progress" states.
- **Changed:** Render AI naturalist analysis as paragraphs instead of bullet lists.
- **Fixed:** Persist deep video analysis label/score on manual reclassification so the UI shows the species.
- **Fixed:** Added missing language options to the header language selector.

## [2.6.6] - 2026-01-25

- **Added:** Standardized AI Naturalist responses to structured Markdown headings (`Appearance`, `Behavior`, `Naturalist Note`, `Seasonal Context`).
- **Added:** AI analysis can prefer clip frames (`use_clip`, `frame_count`) and falls back to snapshots.
- **Added:** Leaderboard hero now shows species blurb and “Read more” link (Wikipedia/iNaturalist).
- **Added:** Guest mode documentation in README and docs, plus About page feature entry.
- **Added:** BirdNET status exposed to guests so the Recent Audio panel can show in public view.
- **Changed:** Leaderboard chart now uses fixed dimensions to avoid NaN sizing/overlap issues.
- **Fixed:** `docker-compose.dev.yml` restored and aligned with prod/base configuration.
- **Fixed:** Added missing error boundary translation keys across non-English locales.
- **Fixed:** Removed stray `common.edit` key from Chinese locale.

## [2.6.5] - 2026-01-24

- **Changed:** Version bump to 2.6.5.
# 2.8.5

- Fixed Explorer manual-tag species search so alias-style labels like `Great tit`, `Great tit (Parus major)`, and `Parus major (Great tit)` collapse to a single canonical selectable species entry instead of showing duplicates.
- Added bulk manual tagging in the Explorer with multi-select support and a shared backend bulk-tag endpoint that reuses the existing taxonomy/audio/manual-feedback flow.
