# Layout Patterns

This is the design language the dashboard, the observation flow and the About page were rebuilt
in. It exists so the next person, or the next agent, extends those screens instead of inventing a
fourth style beside them.

It sits under [`ui-ux.md`](ui-ux.md), which remains the authority on heuristics, WCAG 2.2 AA and
Refactoring UI craft. Where this file is more specific, follow this file. Where it is silent,
follow `ui-ux.md`.

---

## 1. The rules that produced these screens

Capture status, time and confidence badges use `BadgeHint` for explanations on
hover, keyboard focus and tap. Existing action buttons use the `explanation`
action so their click keeps its original effect. Escape closes the explanation
before its enclosing panel; scrolling a badge out of view closes its explanation.
Keep badges above the card's record-opening overlay. The orange missing-upstream
warning means Frigate no longer has the event or media; it does not express
uncertainty about the bird's identity. A matching-call badge describes audio evidence.
A badge set in a line of small text takes `target`, a full 44px touch target that does not make
the line taller. On a phone the Field Log's lines are too close for that, so its confidence and
matching-call markers stay plain words there; the record and the wider layout explain them.

Six decisions carry most of the design. Apply them before reaching for a component.

### 1.1 One window per surface

Every number on a screen describes the same slice of time. The dashboard says "Today" and then
counts visits, species, unresolved detections, camera activity and audio calls over the same 24
hours, via `withinDeskWindow()`. A screen whose header says one thing and whose cards count
another is broken even when every figure is individually correct.

When you add a panel, take the already-windowed list, not `detectionsStore.detections`.

### 1.2 The object is the visit, not the frame

Frigate emits several frames per approach. Users see birds, not frames. `groupDetectionsIntoVisits()`
folds frames of one species on one camera within ten minutes into one row that shows the clearest
frame and the best score. Anything that lists detections to a person groups first. A visit carries
what its frames established: it needs a person only if every frame does, and it is confirmed by a
matching call if any frame was, and the row says so in words ("matching call") so the header's
cross-confirmed count and the rows beneath it agree.

When one capture contains several birds, keep the Frigate event as the parent record. Count
localized birds from one analyzed frame as child observations, so repeated sampled frames do not
inflate the count. Show that count separately from visits and name its coverage: it only includes
captures analyzed with the high-quality crop model. A detector estimate needs visible boxes and
an owner correction path because it can miss birds or mark other objects.
Frigate's event box localizes its one tracked bird; it is not a scene-wide list. The local crop
detector scans the full frame and overlapping tiles on large high-resolution scenes for additional
birds. When it is unavailable, the UI must say that only the Frigate hint could be counted.
The eight classified photo crops per frame are a performance limit on photograph choices, not a
limit on counted detector boxes. The count still reflects only birds the detector localized in an
analyzed frame, so it must not be presented as an exact census.

The counted frame need not be the photograph's frame. `CountedBirds` resolves the exact retained
full frame (same clip variant, frame index and, where the observation names it, candidate) and
outlines birds only on its full-resolution image, whose decoded size is the boxes' coordinate
space. A thumbnail, a possibly cropped Frigate fallback, an ambiguous match or a box outside the
decoded size withholds the outlines and says why; the list stays. Each bird's thumbnail is cut
from that frame by CSS, so it costs no request, and hovering, focusing or choosing its row
highlights it on the frame. Drawn boxes are never controls; the rows are. Repeated species are
told apart by position from the left. The field log reports a visit's busiest single capture
("3 birds in one capture") from the owner-only `bird_summary`, never a sum across repeat frames,
and says nothing for a capture with no stored birds, because not counted is not zero.
Use the server's `is_unknown` decision on each bird so configured unknown labels and
noncanonical taxa agree with the field log. Unrelated parent/SSE patches must not overwrite
the summary from an authoritative event read. Background HQ counts are picked up by the
existing visible-owner checks (once a minute), using stale and single-flight guards. Guests
add no count reads, and completions do not trigger one request per capture. An open record
rereads its scene when that authoritative count changes; superseded reads cannot apply.

An uncertain counted bird can use the accepted visit identity only when its own guess agrees
and Frigate's retained tracked box uniquely identifies it in that same frame. Label this source
as the visit and keep the separate crop score in the evidence. Other birds and owner corrections
keep their own identity. Both counted-bird editors use the shared common/scientific species
search; require a selected complete species and discard searches from an earlier capture or edit.

### 1.3 Say what needs a human, and say why

Work that is waiting is first-class: the review queue is a docked card with a count, not a filter
someone has to think to apply. A flagged row states its reason in words ("Below the naming
threshold"), never by colour alone.

Amber is reserved for "this needs a person". It is not decoration and it is not a second accent.
Green means confirmed or healthy, brand blue means normal emphasis. A row is never coloured to
mean "recent" or "interesting".

Success is therefore its own semantic scale, `success-*`, and never the theme's secondary accent.
`accent-*` is a brand colour: the classic theme paints it emerald and the shipped bluetit theme
paints it amber. Anything meaning confirmed, passed, healthy, connected or verified must use
`success-*` so it stays green in every theme. A theme may repaint `--accent-*`; it must never
define `--success-*`.

### 1.4 Density is affordable only with a way to look closer

Small thumbnails let a day fit on a screen, and a 34px thumbnail cannot settle whether a 56% blur
is a Dunnock. So every small capture opens: hover or keyboard focus expands `DetectionPreview` to
the full frame with score, camera, time and conditions. Density plus an escape hatch beats a large
hero that only ever shows one record.

### 1.5 Never claim health you have not measured

A status chip is bound to a real signal or it does not exist. `InstancePipeline` shows `unknown`
when a status call fails and shows no chip at all for steps with no status source. Media degrades
to a same-size placeholder, never a hole that shifts the row.

The dashboard's audio-versus-camera card exists because being honest that two sensors never
corroborate each other is more useful than hiding it.

### 1.6 Show the evidence at the size the decision needs

When a screen asks someone to judge a machine's output, the evidence gets the larger half and the
controls get the smaller one. The observation review shows the exact input the classifier scored
and lets you compare it against the original upload, because that is how you separate a bad crop
from a bad classification. State the model, the provider and the input; do not leave them implied
by a badge.

---

## 2. Page shapes

Four shapes cover the app. Pick one; do not blend them.

Explorer's filter rail puts species search and its scrollable list first. Date, other
filters and cameras use native collapsible sections, initially closed. Applied filters
stay visible as removable tokens. The rail scrolls when expanded sections exceed the
available height, so selecting a species never shrinks its list to zero. Phones use the
same ordering behind the Filters button.

### Desk (Dashboard)

```
day bar: label, 4 to 6 inline metrics, live indicator
[ primary log, 1.55fr ]        [ context rail, 0.7fr ]
                                queue card (the work)
                                at the feeder now (cameras, conditions), heard
                                reference (activity pulse, top visitors)
```

The rail is ordered by urgency, not by data source: what needs you, then what is running, then
what is merely interesting. Every rail section opens the same way, a small display heading with an
icon and a muted line naming the window (the desk's rolling 24 hours, which the day bar names too),
and sections are separated by space rather than rules. Counts there are visits, from the day
summary, never the loaded page of detections, which undercounts on a busy day. The primary column is one list, not a grid of cards.

### Evidence (Add observation)

```
slim bar: subject, status, escape hatch
[ media, 1.35fr ]              [ decision rail, 0.85fr ]
```

Chrome is a single row. Progress is shown, but it does not get a sidebar. The decision rail holds
candidates and the confirm action, and the confirm action names the thing it will do
("Add House Sparrow"), never "Save".

### Record (a detection)

```
slim bar: subject, camera, time, close
[ media, 1.1fr ]               [ decision rail, 1fr ]
  photograph                     identification, stated once
  frame strip                    confirm / pick a different species / score again
                                 supporting analysis, facts, then Details
```

The photograph is always the crop. The whole scene is a look, not a mode: hover or focus on
the photograph peeks at it with the chosen crop outlined and labeled. Other distinct retained crop
regions from that same frame are outlined too; this shows available evidence, not a bird count.
A click pins the peek, and only the pinned state
offers "Use the whole scene as the photograph". Beneath the photograph is one strip of the
visit's moments in time order (`FrameStrip`), normally one thumbnail per moment; where a frame
came from is not shown, and framings of the same bird fold into it. If separate birds share a
frame, each spatially distinct crop has its own photo choice and tentative model read. Each
thumbnail opens a pop-out on hover or focus with the photograph at decision size and one action
to use that photograph without changing the identification.
There is no Best crop / Full frame switch and no preview-then-save step (#256). The peek is
`WholeScenePeek` in `utils/whole-scene-peek.svelte.ts`, and the review queue uses the same one, and
the same `FrameStrip` beneath its photograph, so every frame kept from a visit is there to decide
with; only regeneration stays on the full record. The review queue keeps the species heading
below the photograph and above the frame strip on every screen size, using the same common and
scientific naming preferences as the full record.
On a phone the comparison pop-out is a sheet at the foot of the screen with a backdrop and its
own Close, because there is no hover to lose.

Beneath the identification, `TaxonomyLineage` shows where the bird sits: one line from class to
species with each rank named, the family's species worldwide against those seen here, and "Open
the family tree". It shows nothing when the catalogue does not hold the bird; a missing lineage is
not an error worth the space. `FamilyTreeDialog` is the full view: a horizontal tree centred on
the bird, as taxonomy trees are usually drawn, with Animalia and Chordata as a breadcrumb rather
than branches. Its path is open and amber; groups seen at this feeder are green and say how many;
everything else in an open group is summed in one "more" node. A group's label sits above its node
so branches never cross it, and every node is a keyboard button with `aria-expanded`. The fan and
the outline list read the same visible tree, and a narrow screen opens on the outline until the
reader picks another. Every name in the ladder, the tree and the outline opens a `TaxonCard` under
the §4 contract, one card per surface driven by `utils/taxon-peek.svelte.ts`: a species shows its
reference photograph (one species-information request per species per page, through
`utils/taxon-pictures.ts`), a group shows its size and what was seen here. A group never asks for a
picture, because the species-information route would cache it as a species. Selecting a species,
which has nothing to open, pins its card; the species details show the same ladder. The tree is a ranked classification, and the footer
says so: it shows grouping, not divergence.

### Standing (Leaderboard)

```
span bar: day, week, month, total · seen, heard, both
wall: the leader named, the share bar as its navigation, then a contact sheet of this feeder's own visits
flagged species: probable misidentifications, named apart for a person to check
standing band: species, detections, busiest hour, heard or confirmed, rising, most recent
rankings (with evidence), then analytics
```

A leaderboard is only as good as its identifications, so the rankings say what stands behind each
species besides the classifier: confirmed by the owner, heard by BirdNET in the same window, or the
camera alone (`leaderboard/evidence.ts`). A trend is claimed only when the history covers the whole
previous window (`previous_window_complete` from the route); otherwise the page says when records
start. Rankings count visits (`window_visit_count`, the shared server rule of a 60-second inactivity gap after the latest verified event end,
with capture time as the fallback), and only the all-time view, which has no visit counts, says detections.
The timeline and the composition chart share one colour per species
(`leaderboard/species-palette.ts`, validated for colour-blind separation on both surfaces).

The wall (`CaptureWall`) opens the page. Its header names the leading species, and under it the
share bar is the wall's navigation: one segment per species in its chart colour, sized by its share,
then the species beyond the list summed as "other species" and the flagged ones as "Needs a check"
(`SpeciesChecks`, which lists them for a person to review). Hovering or focusing a segment opens it
out to say its share and count and lights that species' visits while the rest step back; a click
pins the highlight (a second click lets go, Escape too) and offers "Open" for the species, which is
all touch has. A highlight always points at something: a segment no longer in the bar, or a species
with no visit on the wall, dims nothing. Ink on each segment is chosen for contrast, and the focus
ring is two-toned so it shows on every colour.

Under the bar is a contact sheet of this feeder's own visits in the window, newest first, one stored
crop per visit, packed densely like a photo library: a fixed number of rows (more once "Show more
visits" is chosen) of square cells whose size comes from the width alone. Visits are folded by the
shared visit rule (`utils/visit-grouping.ts`) from the owner's capture list, cut to the window's own
start and end, and shown by their strongest frame. A capture is matched to its species by the
ranking's key, name, taxon or scientific name, so scientific-first naming and owner renames still
light and open the right species. The leading species' strongest visits are drawn at four times the
area, a number that grows with the wall (none under eight visits, at most four). `packTiles` lays
them out the way the grid will and keeps the longest run with no hole, trying the last large tiles
small when that shows more of the wall, so a full wall ends in a full row and a small one keeps
every visit. Only stored crops are shown: a whole scene at card size is a picture of a feeder, so the
backend leaves it out, and a photograph that fails to load leaves the wall rather than leaving a
hole. A species flagged as a probable misidentification is never put on show, and with fewer than
eight visits there is no wall. A guest's photographs share the request budget, so a guest's wall is
capped.

Hovering or focusing a visit rings it and draws its photograph in a little closer; the tile never
changes size and nothing around it moves. After a short intent delay a pop-out opens beside it under
the hover contract (§4): the larger photograph, rank, the common and scientific names, the
classifier's confidence, when and where it was seen, how many frames the visit holds and whether a
clip exists. Once one is open, the next visit's pop-out is immediate and the pop-out glides to it.
It sits against the viewport on the side that points into the wall, follows its tile while the page
scrolls, can be reached with the pointer so its text can be read, and closes on Escape, on leaving,
or when its tile leaves the screen. On touch a tap opens the species. The wall has one Tab stop and
the arrow keys, Home and End move between visits. It rises into place once on first paint and
stands still under reduced motion.

The pop-out plays a film once one is made (`VisitFilm`): four silent seconds of the visit, cut
from Frigate's recording around the moment of the visit's best snapshot and framed on the bird, so
the card is sharp where a stored crop is a few hundred pixels across. The photograph is always
underneath, so a missing film is a photograph and the layout never moves. A film is fetched only
when its card nears the viewport, plays only while visible, is downloaded once however many copies
of the card show it (`utils/visit-films.ts`), and is never fetched under reduced motion or a
data-saver connection. Changing either preference while the page is open releases the film and
keeps the photograph. Frigate keeps recordings for days, so older visits keep their photographs.
Films require a proven recording moment and crop bound to the saved image. New final-snapshot
crops keep that evidence, including a selected alternative bird. Older photographs and video
choices without exact recording alignment stay still: a film from the original tracked bird
must not cover a photograph of a different bird. Changing the photograph invalidates the film.

### Reference (About)

```
portrait: since when, visits and species, the busiest day and the newest arrival, beside the latest visit
colophon: what this is, in plain sentences
live diagram: the standard flow, annotated with this instance's state
build detail: what to quote in an issue report
credits
```

Sections are ordered by reader: visitor, then anyone, then owner. Do not add a feature grid; the
readme and `docs/` hold the feature list.

The portrait (`FeederPortrait`, `/api/about/portrait`) is one calm block of facts the feeder has
measured: when it started, its visits (the shared 60-second visit rule) and species to date, its
busiest day in the viewer's own calendar days, and its newest arrival, which must have been seen at
least three times or confirmed so a single misidentification is never announced. Beside them is
the latest visit with a stored crop, which plays its film once one is made and opens its record. A
guest sees the shared window only, and the heading says so, so a short window never reads as a
young feeder. A shared-history change clears the guest's portrait immediately and reloads its facts
and latest visit; an older response cannot restore withdrawn media. The install count beneath is a cached read of the telemetry worker's public summary,
off with update checks, and absent rather than zero when unknown.

---

## 3. Components and where they belong

| Component | Use for | Do not |
| --- | --- | --- |
| `FieldLog` | The Dashboard's chronological visit log and its identification actions | Use for operational history or search results; Health and Explorer own those |
| `HealthActivityTimeline` | The Health page's chronological account of recorded visits, expected filtering and fault drops, with each outcome stated explicitly | Turn it into an identification queue; the Dashboard owns outstanding work |
| `FieldLogVisitRow` | One visit on the field log's thread, opening from its time onto its captures in the same columns | Add a second disclosure control, or colour capture nodes without also changing their shape |
| `VisitCaptures` | A visit's chronological captures: `inline` inside a Health row, `footer` closing an Explorer card or row | Render for a single capture, repeat the visit's camera or day on each line, or sum birds across captures |
| `FilteredFramePreview` | A frame the classifier rejected, which has no detection record | Use where a `Detection` exists; that is `DetectionPreview` |
| `DetectionPreview` | Any thumbnail under ~64px | Use as a click target for navigation; click opens the record |
| `FrameStrip` | The moments of one visit inside its record, with the comparison pop-out | Show framing variants of one moment side by side; the pop-out carries the framing |
| `ReviewQueueCard` | Outstanding decisions | Use for notifications or job progress |
| `DayBar` | The window label plus its headline metrics | Add a seventh metric; cut one instead |
| `DeskContextCards` | Standing operational context | Put actions in it |
| `TopVisitors` | A full-width band | Place it in the context rail; it lays out horizontally and compresses badly |
| `InstancePipeline` | Deployment state as a flow | Use it as a settings surface |
| `ReviewQueueModal` | Working a queue item by item | Use for viewing one record; that is `DetectionModal` |
| `ActivityHeatmap` | A weekday by hour grid that reads a slot on hover, tap or arrow keys, with hour and day totals in its margins | Rely on native `title` tooltips; they arrive late and never on touch |

Server grouping lives in `backend/app/repositories/visit_repository.py`, shared with statistics.
`VisitCaptures` expands any visit into bounded chronological pages of original records; no inference
runs to group history. A visit and its captures are one object. Explorer card footers sit inside the card's single
rounded frame. The record action covers the record section; capture actions remain separate. In the field log
(`FieldLogVisitRow`) a visit of several captures opens from its time, which carries a chevron and
is a real button with `aria-expanded`. The row states "13 captures" in words beside the name, apart
from the busiest capture's bird count, so it costs no extra line. Its captures join the same thread
in the same columns, through CSS subgrid: the time to the second, the node, the thumbnail (which
opens that exact capture), its own species and scientific name, any note, the score under the visit's score, and the clip under Open.
A visit's node is solid; a capture's is hollow on a tinted stretch of the line, and the capture
used as the visit photo is filled and says "Visit photo", so the two kinds differ by shape,
position and words as well as colour. A single-capture visit has no list and keeps its Open
action. Each line names its own species with the shared naming preferences and states its own
confidence. Camera and day stay at visit level. The camera chip appears on log rows only when the log holds more than one camera.
`VisitCaptureList` reads the first page when a visit first opens and reuses it until the visit,
window or access changes; Health rows and Explorer cards use the same loader through
`VisitCaptures`. Explorer grids use a native floating capture panel above the cards, so no grid row moves
when it opens. Its control works by click, touch or keyboard; Escape, an outside click or
Close dismiss it. The panel stays within the viewport and scrolls long lists. Thumbnail
previews portal into the panel's top layer. Explorer list and Health layouts stay inline. `FrameStrip` removes unwanted photo choices reversibly with Undo while retaining
counting evidence. Recent species sightings open exact detection links.

Loading never claims a state. Until the day has been read, the field log shows placeholder rows
in the anatomy and height of real rows, the day bar shows placeholders instead of zeros, the review
queue does not say "Nothing waiting", and the camera list does not say none are reporting. A first
read that fails says so with a retry. Every placeholder stands still under reduced motion.

Pure logic lives in `apps/ui/src/lib/utils/`: `visit-grouping.ts` (summary adapters, fixture grouping, the desk window and
threshold-aware review decisions), `review-queue.ts` (queue selection and ordering),
`dashboard-cameras.ts` (configured-camera scope and visit counts), `pipeline-health.ts` (which
dropped events are faults and which are expected filtering) and `health-timeline.ts` (merging kept
visits, filtered frames and fault drops into one operational thread). New decision rules go there,
with unit tests, and never inside a component.

The review threshold comes from the saved `classification_threshold` setting. Do not copy its
current value into frontend code. Until owner settings load, explicitly unknown detections still
need review, but a named detection is not flagged against an invented threshold.

**Pickers open on what is likely, not on what is first.** The classifier knows eleven thousand
labels and sorts them alphabetically, so an unfiltered list opens on earthworms and spiders. Any
species picker offers what this feeder has actually recorded, most frequent first, and searches the
full list only once someone types.

---

## 4. The hover pop-out contract

Any preview that opens on hover must satisfy all of this, because hover alone fails WCAG 2.2 AA:

- Opens on hover **and** on focus, so keyboards reach it. Hover means `pointerenter` from a
  hovering pointer (`event.pointerType !== 'touch'`), focus means keyboard focus
  (`:focus-visible`). A touch browser replays a tap as mouseenter, then on Chrome a focus (iOS
  Safari does not focus a button on tap), then click. A pop-out that opened on the replay is
  either closed by the click (when it has a backdrop) or swallows the click (iOS, when a
  mouseenter handler changes the DOM), so on touch the click alone opens it. `DetectionPreview`
  and `FilteredFramePreview` follow the same rule.
- Stays open while the pointer travels into the panel. `DetectionPreview` and `FrameStrip` use a 120ms close grace
  window for exactly this (SC 1.4.13, "hoverable").
- Dismisses on `Escape` without moving focus elsewhere unexpectedly.
- Reuses the image already fetched. A preview must not cost a second request.
- Respects `prefers-reduced-motion`: it appears without the scale transition.
- The trigger is a real `button` with `aria-expanded` and a visible focus ring.

Model any new popover on this and on `CameraStatus.svelte`, which established the pattern.
A pop-out that holds a control (`FrameStrip`) is a `group` named for its subject, not a `tooltip`, and
its Escape closes the pop-out before the dialog behind it.

Below 640px `FrameStrip`'s pop-out is a bottom sheet with a backdrop and its own Close. A sheet never
opens on hover: its backdrop would arrive under the pointer as a `mouseleave` and close it again. It
opens by tap or keyboard, and it closes by its backdrop, its Close, Escape, or focus moving elsewhere,
never by the pointer drifting off the strip.

---

## 5. Writing

The product's voice is dry, first person where a person is speaking, and understated. The readme
sets it: *"A personal project built with AI-assisted coding... I saw an opportunity to learn and
build something better."*

- **No em dashes.** Use a comma, a colon, a semicolon or a full stop.
- Name a control by its effect. "Identify", "Add House Sparrow", "Work through the queue".
- Empty states say what is true and what is next: "Every visit today has a species. Nothing waiting
  on you." Never a bare "No data".
- State an unknown as unknown. Do not round it up to healthy.
- No nature-documentary register. "A camera pointed at a feeder, and a great deal of curiosity" is
  the wrong voice. "A feeder camera, a classifier, and a database" is closer; the plainest correct
  sentence is usually right.
- Identifiers are not copy. Table names, topics and model ids render as literal monospace strings
  and never go through i18n.
- Every user-facing string goes through `svelte-i18n` with a `{ default: '…' }` fallback, and lands
  in all nine locales. The locale audit enforces key parity; genuine cognates and product names go
  in `locales.identical-baseline.json`.

---

## 6. Visual details worth copying

- **Type**: Bricolage Grotesque (`font-display`) for headings and figures, Instrument Sans for
  everything else. `tabular-nums` wherever digits align in a column.
- **Photographs in a fixed box**: fill the box (`object-cover`) unless that would cut away more
  than a quarter of the photo, as for a tall crop of a woodpecker on a pole. Then show it whole
  over a soft blurred copy of itself. `utils/photo-fit.ts` decides from the loaded image; the
  detection card and the record's photograph use it (#481).
- **Panels**: `card-base` for standing surfaces. Rows inside a list are separated by hairlines,
  not by nested cards.
- **Flagged rows**: a left-to-right amber wash plus a state dot plus a worded reason. All three.
- **Score**: a percentage in a tone band (under 60 amber, under 85 brand, above 85 green) and a
  3px bar. Never the bar alone. **Exception:** a frame the filter rejected scores under 60 by
  definition and wants nothing from anyone, so it renders in slate with its reason in words. Amber
  on those rows would contradict 1.3 and put seven of them under a heading saying nothing failed.
- **Touch targets**: `min-h-11` on anything interactive, including chips and inline actions.
- **Review overlay**: the queue pins the underlying page at its current scroll position while open and restores it on close. Its backdrop covers the viewport even when the page has scrollbars. Opening the full record releases the queue lock before the record takes its own lock; closing the record returns to the same page position.
- **Text reflow**: capture detail sheets fit 320px at 200% text. Media flex items need `min-w-0` so an aspect ratio plus a minimum height cannot widen the sheet in Safari. Fact labels, technical disclosure chrome and footer controls wrap when enlarged text no longer fits; complete names remain readable and controls retain their touch-target floor. Check the actual modal in Chromium and WebKit, including a full-resolution whole-scene peek and its outline geometry.
- **Disclosures**: a collapsible section is not required to look like every other one — a terminal
  panel and an inline "show technical details" link are different things — but all of them owe the
  reader the same three signals: it says whether it is open (a chevron that rotates on `group-open`,
  or wording that changes between Show and Hide), it clears the touch-target floor, and it shows
  keyboard focus. `apps/ui/src/lib/components/disclosure-affordance.test.ts` holds every native
  `<summary>` to that.
- **Media**: fixed aspect, `loading="lazy"`, and an `onerror` placeholder of identical size.

---

## 7. Before you ship a layout change

1. Does every number on the screen describe the same window?
2. Does the screen group frames into visits before showing them?
3. Is outstanding work visible without a filter, and does a flag say why in words?
4. Can every small image be opened, by mouse and by keyboard, with Escape to close?
5. Does anything claim a state it has not measured?
6. Do the new strings exist in all nine locales, free of em dashes, naming controls by effect?
7. `npm run check` clean, `npm test` green, and a layout test asserting the structural intent.
