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
hover, keyboard focus and tap. A badge that shows words is named by those words and the
explanation is its description; `label` names a badge that is only an icon. Existing action buttons use the `explanation`
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

Every number on a screen describes the same slice of time. The dashboard says "Last 24 hours" and
then counts visits, species, unresolved detections, camera activity and audio calls over the same
rolling 24 hours, via `withinDeskWindow()`. Every line on the desk names that window the same way:
the field log's "earlier visits in the last 24 hours", the review queue's empty state and the log's
empty state, never "today" or "of the day". A screen whose header says one thing and whose cards
count another is broken even when every figure is individually correct.

A link that leaves the page says where it goes and points onward, not down: "9 earlier visits in
the last 24 hours, open in Explorer" with a right chevron. The Explorer's address holds whole days (a
preset or a custom range of dates), not a rolling window, so the link opens it unfiltered rather
than on a window that is not the desk's.

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

The field log also says **Owner confirmed**, with a checkmark, when an owner
explicitly confirmed the visit species in a visible capture. This is separate from
model confidence and matching calls; a high score or manual upload alone does not
establish owner confirmation. Server visit summaries carry the aggregate even
when the chosen favourite or latest capture was not the confirmed one. Unresolved
names and captures excluded by the active visibility filters do not establish the marker. The desktop badge explains
this on hover or keyboard focus; phones keep a plain worded marker.

### 1.3 Say what needs a human, and say why

Work that is waiting is first-class: the review queue is a docked card with a count, not a filter
someone has to think to apply. A flagged row states its reason in words ("Below the naming
threshold"), never by colour alone.

"Needs your call" holds every kind of waiting work in the desk's window, not only the visits. It
also names the species the leaderboard's range check flags over the same 24 hours
(`windowSpeciesChecks()` in `leaderboard/species-checks.ts`, the predicate the Species page's
**Needs a check** uses), links to them at `/species?span=day#checks`, and offers the kept-bird
action through the same `KeptBirdOffers` component. `needsYourCall()` in
`utils/needs-your-call.ts` decides what the card may say: each reading (visits, species checks)
is loading, unavailable, clear, waiting or stale on its own, and "Nothing waiting on you" appears
only when both were measured and are zero. A leaderboard answer measures the species checks only
when its `nearby_check` is `checked` (`readRangeCheck()`): a check that is switched off is no
pending work and no error, so the card says only that every visit has a species; one that could not
run, or that only has an eBird report past its six-hour cache, is unavailable. Work from an earlier
read whose refresh failed stays on screen, marked as possibly out of date with Try again. On both
the Dashboard and the Species page a kept bird's offer closes as soon as its move succeeds, through
the shared `DomesticBirdOffers` (`utils/domestic-bird-offers.svelte.ts`), and returns only if a
fresh read flags it again, whatever the reload does. The day bar's "nothing to review" follows the
same rule.

Amber is reserved for "this needs a person". It is not decoration and it is not a second accent.
Green means confirmed or healthy, brand blue means normal emphasis. A row is never coloured to
mean "recent" or "interesting".

Success and attention are therefore semantic tones of their own, never the brand. Anything
meaning confirmed, passed, healthy, connected or verified uses the `ok` status tone
(`text-status-ok`, `StatusChip tone="ok"`) so it stays green in every theme. Anything meaning
"this needs a person" (a flagged row, the review queue, a warning toast, a degraded subsystem) uses
the `attention` tone, which is amber in every theme. Both are defined once in `app.css`; a colour
theme repaints the brand (and with it `accent`), never a status tone
([`design-tokens.md`](design-tokens.md)). The older `success-*` and `attention-*` step scales still
appear in screens not yet moved onto the tokens, under the same rule.

The palette is closed. Component code paints with brand, `success-*`, `attention-*`, rose (and the
kit's red danger buttons) and slate, and nothing else: no raw `amber-*`, and no
second accent such as indigo, sky or cyan to make a panel look distinct. A panel is told apart by
its heading, not its tint. The few reasons to step outside are named, with their reason, in
`PALETTE_EXCEPTIONS` (`colour-language.layout.test.ts`): a theme picker's swatches, categorical
chart series that are always named, the rain band on the activity chart, and the orange
missing-upstream mark. An outline drawn on a photograph (a counted bird, the chosen crop, a
detector's box) uses the one `evidence` colour, which holds against plumage and foliage in every
theme. `attention-*` itself is allowed only in the components listed in `ATTENTION_COMPONENTS`,
each with the work it waits on, so a new screen cannot reach for amber without saying why.

Work in flight needs nobody, so a running or queued job takes the brand colour, not amber. A
reported status (healthy, running, degraded, failed, unknown) takes its tone and its translated,
sentence-case label from `utils/status-tone.ts`: brand for running, amber for attention, rose for a
failure, green for healthy and slate for a state that was not measured. The raw backend word
appears only in a `title`.

White text needs a fill of `brand-700` or darker. `brand-500` under white is 2.49:1 in classic and
3.68:1 in bluetit, so a chosen option filled with brand colour uses `bg-brand-700` (as `btn-primary`
does) or the kit button itself.

### 1.4 Density is affordable only with a way to look closer

Small thumbnails let a day fit on a screen, and a 34px thumbnail cannot settle whether a 56% blur
is a Dunnock. So every small capture opens: hover or keyboard focus expands `DetectionPreview` to
the full frame with score, camera, time and conditions. Density plus an escape hatch beats a large
hero that only ever shows one record. A Garden animal's thumbnail opens the same way through
`GardenCapturePreview`: its saved crop, else its snapshot, with the Garden name, score, state, time
and camera. It previews only the media the server listed for the reader, so a visitor sees no
pop-out for a photo the owner does not share; that thumbnail stays a plain frame in the same cell.

### 1.5 Never claim health you have not measured

A status chip is bound to a real signal or it does not exist. `InstancePipeline` shows `unknown`
when a status call fails and shows no chip at all for steps with no status source. Media degrades
to a same-size placeholder, never a hole that shifts the row.

The dashboard's audio-versus-camera card exists because being honest that two sensors never
corroborate each other is more useful than hiding it.

"Live" is a claim about camera events, not about the page. The sidebar's Frigate events row and the
Dashboard's feed line are green only while the MQTT broker session is measured up
(`utils/live-feed-state.ts`); a broker or Frigate that is down turns them amber in words, and
without a measurement (a guest, or before the first read) they say only that the page is connected
to YA-WAMF.

The sidebar's System status is a list, not a row of icons: each row is a label, the state in words
and a small dot whose shape as well as colour gives the tone (filled circle working, diamond needs a
person, ring off or unknown). The words for every state come from one tested mapping
(`utils/system-status.ts`). Off by choice is neutral, never amber, and one cause is flagged once:
with the broker down, Frigate events is amber and Audio says "Not listening" in neutral ink. The
card is a neutral surface with nothing drawn behind it; resource readings are one muted line of
text with tabular numbers. Its Health link counts open issues from the same store the Health
page lists them from, and says nothing about issues when none is open. The page has one name,
Health, wherever it is linked from. The icon rail shows the same
rows as icons named by the same words. The Health page follows the same rule: its verdict is never healthy while the broker
or Frigate is down, and its MQTT and Frigate rows lead with the connection state, not queue load.
Its subsystems are one ruled list in full-contrast ink, each state a worded chip; a reason code it
knows is said in words with what to try, and the backend's own text sits under Technical details.

A destructive question states only a count it read. A confirmation whose message names a figure
takes a `reading` (`stores/confirm_dialog.svelte.ts`): it opens saying what it is counting, cannot
be confirmed until the read lands, and asks without the number when the read fails. Never fall
back to zero. The record says "Frigate no longer has this event" only on a not-found answer
(`utils/frigate-event-reading.ts`); a Frigate that could not be asked gets its own cause and next
step. A wait is named for what it waits on and is bounded: the wizard's Cameras step is ready once
the settings load, and asks Frigate for at most 8 seconds beside it. The model's state is one
reading everywhere: `identificationStatus()` words the sentence, and `settings/model-readiness.ts`
names the state in one vocabulary (checking, missing, queued, validating, failed, loading, ready,
running, unknown) with one word and one tone each (`readinessLabel`, `readinessTone`). The server
reads the same runtime report through `services/model_readiness.py`, and both are held to
`tests/fixtures/model_readiness_cases.json`. Settings › Identifying birds, the wizard's review, About's
pipeline and a Garden capture's wait all call that one rule (`classifierReadiness`); none derives
its own. Three things keep them agreeing:

- **Selected is not running.** "In use" is said only of the selected model when it is running. A
  selected model in any other state says that state ("Chosen · Could not load").
- **Work in progress is the server's to report.** A download or a hardware check runs on the
  server, so the server is the authority (`GET /api/models/activity`), and
  `stores/model_activity.svelte.ts` keeps every surface reconciled with it while one is shown: in
  this tab or another, whichever page started the work, and it ends everywhere when it ends there.
  A page that starts work records a hint so its own button answers at once, with the phase taken
  from the stage that is running (`activityPhase`); the hint lasts only until the server reports
  that model. No surface keeps its own memory of work in progress.
- **A second reading stays a second reading.** About reports inference health beside the model's
  state, never as the state. A Garden check blocked by something other than its model (species
  data that could not be read, a worker that would not stop) keeps that cause and its own way out
  (`gardenCheckState`); it is never a model that "could not load".

A model that is only chosen is never called configured or installed, and a classifier that
answered with no evidence reads "Not reported". A state has one action: a download for a missing
model, a recovery for a failed one (`chosenRecovery`, which gives a bundled model one too). While
the chosen model needs it, that is the page's only primary button (`setupEmphasis`). A wait a model
is blocking names the blocker and links to its setup, whenever the model is what is missing. An
owner is never left stuck behind a model: Garden's dismissal is reversible and is never gated, and
manual override (`gardenManualOverride`) waits only while the automatic check is on its way (its
status being read, its model downloading). It opens once the check can run, and also once the check
is known not to be able to run here, with a note that the owner decides by hand. After a read that
failed it stays closed, says so and offers a retry, because nothing was measured. Reassurance needs a reading too: the
backend-down screens say nothing about the data they could not ask about.

An amount needs a price as well as a count. Settings → Sharing & integrations shows a cost only for usage that has a
rate (`settings/ai-cost.ts`): a model without one is "Not priced", usage with no prices is "Cost not
estimated: add prices", and a total over part of the usage states the requests it covers. About's
list of what leaves the network is built from the features that send each request
(`utils/outbound-requests.ts`), names who sends it (this server, or each viewer's browser) and what
it sends, and makes no promise that the list is all there is. A setting a guest cannot read is
"Owner only", never "Disabled". A row reads On only when the request can really be made: a
notification channel needs its credentials as well as its switch. The rows are held to one
registry, [`backend/outbound_requests.json`](../../backend/outbound_requests.json): a backend
module that can send a request, or a new outside host, has to be entered there, each entry has to
have a row, and each row's disclosures are asserted in every locale
(`i18n/outbound-disclosures.test.ts`). Adding a request therefore means adding all three.

A page that reads data keeps four states apart: loading, read and empty, failed, and stale. Only a
reading may show a number, so a pending or failed read never shows a zero or "no activity"; a
failure is said in the page's own sentence with the next step, the server's words behind a
disclosure; and a refresh that fails keeps the earlier reading with the time it was read
(Audio history, `pages/audio-history-state.ts`). A progress bar is drawn only for a measured total.

### 1.6 Show the evidence at the size the decision needs

When a screen asks someone to judge a machine's output, the evidence gets the larger half and the
controls get the smaller one. The observation review shows the exact input the classifier scored
and lets you compare it against the original upload, because that is how you separate a bad crop
from a bad classification. State the model, the provider and the input; do not leave them implied
by a badge.

---

## 2. Page shapes

Four shapes cover the app. Pick one; do not blend them.

Explorer's filter rail orders filters by how often they change. Choices set once and
left (**Visitors**, **Show**) are compact switches that explain only the chosen option
beneath them. **Visitors** has three names of unequal length, so its options take a line each:
equal segments with whole words in every language and text size. **When** follows, always open. The species list shows the eight most
recorded species, plus any chosen one, then **Show all N species**. One search box
(`ExplorerSearch`, a combobox) finds species, groups, cameras, days and record IDs. It is a page
control, not a filter: on a desktop it starts the Explorer's header row, before the view switch,
and stays when the rail is hidden; on a phone it heads the rail, above the results
and beside the **Filters** button. The count has a line of its own at every width (beneath the
header row on a desktop, above the search on a phone): it arrives after the page is drawn and
its length depends on what was found, so nothing shares its row that a longer count could wrap.
A figure that would be zero is left out of the count rather than stated. The header row holds the
page's controls on a desktop (**Heard calls**, the rail toggle, **Cards**/**List**,
**Multi-select**); below Tailwind's `lg` the view switch sits beside the **Filters** button and
the two used less often open with the filters under **View**, each control written once and
placed by the same `MediaQuery`. Leaving selection is **Done** on the selection bar. The listening
history is a sidebar item, not a second audio button in this row. The first read's placeholders
and the results are separate panes (`{#key}` on the first-load state), so a day strip or notice
that arrives above the results moves nothing already drawn; the day strip is shown only for a page
that spans more than one day, each day as its name and a plain count. Cards and rows take their
place without an entrance animation: a fade leaves every word under contrast while it runs. The page mounts it once and places it with a `MediaQuery` at
Tailwind's `lg`. Each result is one line where the panel allows (name, italic other name, a
`.taxon-rank` label, the count at the end), in a panel as wide as the box; the active result takes
`.choice-active` and a return arrow saying what **Enter** does. Cameras and **Only** stay in native
collapsible sections, initially closed, and their summaries name what is chosen inside. A chosen
row is `.choice-active` with a check, so it reads by weight and shape as well as tint. Only the rail
scrolls, never a list inside it. Applied filters stay
visible as removable tokens, with **Clear all** beside the rail's title. Phones, and a desktop
with the rail hidden, use the same ordering behind the Filters button, which opens them as a modal
sheet in the app's dialog pattern: portalled, named **Filters**, focus moved in and held by
`trapFocus`, the page scroll locked, closed by **Close**, Escape or a press on the dimmed page,
with focus returned to the Filters button. Filters still act at once; the sheet has no Apply. The
filters are written once (a snippet) and drawn in the rail or the sheet. A switch and its token use one name per option (the
subject is **Garden animals**, as Settings names it), and a custom window's token names its
dates ("1 Oct to 28 Oct") under visible **From** and **To** labels. **Cameras** lists the cameras
of the chosen visitors and shows a count only where one was measured for them: bird counts under
**Birds**, none under **Garden animals** or **Both**.

The rail's state lives in the address (`utils/explorer-query.ts`), so a reload, Back/Forward
and a pasted link open the same view. Each change replaces the current history entry rather than
pushing one: Back leaves the page, not each filter tried. Values the rail could not hold are
ignored, owner-only filters are never read for a visitor, and keys the Explorer does not own
(a shared clip's `event`, `share`, `video`) are kept.

Explorer can show heard calls between its visits, from a **Heard calls** switch on the page (off
until a device turns it on, remembered per device like Cards/List, never a setting). Visits stay
the rows. A call that supports a visit the pipeline already confirmed (same species, a mapped
microphone, within the visit widened by the correlation window) is counted on that visit, call by
call ("matching call, 4 calls"), so a bout that runs on past a visit is split at its edge. Every
other call folds per species into bouts across up to five minutes of silence, the default
correlation window, and the bouts gather into one band per gap between two visits: its start time, layered spectrograms,
a heading with its span and counts, a chip per species, and **Show calls**. A band is quieter than
a visit and is placed and labelled by when it began. A filter that only describes camera visits
(camera, favourites, hidden, multiple species, matching call, a species group, confidence order)
hides the calls and says why; an empty span says no calls are stored, never that nothing was
heard. A capture with several species uses the band's shape: **Multiple species**, layered
thumbnail, a chip per species with its count and **Show species**, and no single score.

### Desk (Dashboard)

```
day bar: eyebrow, the window as the page heading (the page's only h1), live indicator
         then every figure for that window in one ruled band (label above figure, scope beneath)
[ primary log, 1.55fr ]        [ context rail, 0.75fr ]
                                Needs your call (the work), heading the rail
                                what is happening:
                                  at the feeder now, heard
                                reference:
                                  activity pulse, notable nearby, top visitors
from 1920px the rail splits into those two columns, under the card that spans both:
[ primary log, 1.4fr ]  [ Needs your call, across both          ]
                        [ happening, 1fr ]  [ reference, 1fr ]
on a phone, one column: the day bar, Needs your call, the log, then the rail
```

The rail is ordered by urgency, not by data source: what needs you, then what is running, then
what is merely interesting. Needs your call comes first in the page itself, so on a phone the work
sits above the log, before anything secondary; from 1280px the grid places it at the head of the
rail, beside the top of the log. On a very wide screen the rail becomes two columns so the log keeps a
readable row; the order inside each holds. Every desk section is a panel (`panel`) that opens the
same way, a display heading with an icon and a muted line naming the window (the desk's rolling 24
hours, which the day bar names too). Counts there are visits, from the day summary, never the
loaded page of detections, which undercounts on a busy day. The primary column is one list, not a
grid of cards and not a hero photograph over a list: every row already opens its full frame. On a
phone the log drops its panel frame so the rows keep their width.

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

The rail's "Identified as" heading names the bird once and titles the dialog. The photograph does
not repeat the name, the common-name control is an action ("Change the common name") rather than a
second statement of it, and a missing classification source is left unsaid rather than reported as
"not recorded". The species route is one secondary button; Confirm is the only primary action.

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

Beneath the identification, `TaxonomyLineage` shows where the bird sits: a ladder from class to
species, one rank per row, each rank named in small tracked capitals (`.taxon-rank`) in a column of
its own and joined to the rank above by one right-angled branch. It shows the family's species
worldwide against those seen here, and "Open the family tree". It shows nothing when the catalogue
does not hold the bird; a missing lineage is not an error worth the space. `FamilyTreeDialog` is the
full view: a horizontal cladogram centred on the bird, with Animalia and Chordata as a ranked
breadcrumb rather than branches and each rank named once at the head of its column. Its path is a
heavy line with solid dots; groups seen at this feeder are green and say how many; everything else
in an open group is summed in one "more" node. A group's label sits above its node so branches never
cross it, and every node is a keyboard button with `aria-expanded`. The tree's whole row is the
click target, 44px tall, not just its glyphs. The tree, the fan and the outline are one ARIA tree
with one tab stop: the arrow keys move through the visible nodes, Right and Left open and close a
group or step into and out of it, and Home and End reach the ends (`taxonomy/tree-navigation.ts`).
A narrow screen opens on the outline until the reader picks another layout. A legend names every
mark, and a mark is never colour alone: this bird is a ringed dot, a closed group carries a plus, a
"more" node is a dashed ring (`TaxonMarker`, one drawing for the tree, the fan, the outline and the
legend).

**Names follow the zoological convention, everywhere a taxon is named** (`taxonomy/nomenclature.ts`,
set through `TaxonNameText`): the genus and every rank beneath it is italic, a genus is capitalised
and an epithet is not, and a family and every rank above it stays upright. A common name is never
italic. The reader's Bird Naming Style decides which name leads: common first with the scientific
name beneath, scientific first with the common name beneath, or the scientific name alone. A common
name that only repeats the scientific one is shown once. Ranks always read from the highest down,
whatever order a source returns them in, and each rank is labelled in words. The tree never
invents what the classification does not hold: an authority and year appear only as the catalogue
stores them (upright, after the italic name, parentheses only where the source wrote them), and
there are no dates or branch lengths and nothing about how individual birds relate.

**It is this feeder's tree.** What the install recorded comes from `/api/taxonomy/facts`, one request
per open level (`utils/taxon-facts.svelte.ts`, one store per surface shared by the ladder, its card and
the tree; decisions in `taxonomy/taxon-facts.ts`). A species node seen here shows this install's own
photograph beside its marker, its visits, and "heard" when BirdNET recorded it. Visits are the shared
visit rule plus confirmed Garden visits; unconfirmed captures and hidden records never count. The
legend names the window the counts cover (all history, or the days shared with visitors).

**Counts are stated one way.** A group says "N species, M seen here" on its node, in its card and in
the outline; a species says "N visits", and its card says "No visits recorded" rather than a zero. A
Garden animal's group says only what was seen ("1 seen here"): its catalogue holds the model's animals,
so its sizes are not worldwide counts.

Every name in the ladder, the tree and the outline opens a `TaxonCard` under the §4 contract, one
card per surface driven by `utils/taxon-peek.svelte.ts`. The card is set like a specimen label, in
this order: the photograph; rank, name in the display face, the second name with its authority; the
heard and IUCN badges, each in words (the category is spelled out with its code, never a colour); what
was recorded here as a row of figures, label above figure (visits, first and last seen, or for a group
its size, visits and last visit), with the window beneath; a three-line description with its provider;
and, for a species, its names in other languages collapsed behind "Names in N languages". The photograph
is this install's own newest stored crop, captioned "Your photo" with its date, falling back to the
reference photograph captioned only "Reference photo" when there is none or it fails to load (the
route's `source` names the summary provider, not necessarily the photograph's, so the card names no
provider). A group is pictured only by its most-seen member's own photograph ("Your photo of
Dunnock"), never by a reference image. Reference lookups go through `utils/taxon-pictures.ts`, once per
taxon per page: a species by its scientific name as the hint, so a mammal is not searched for among
birds, and a family or order by its name and rank, which the route describes only from the taxon of
that exact name and rank and caches apart from species. A genus is never described, because genus
names repeat across kingdoms. A description is shown only when the taxon is its article's subject: the title is the
scientific name, or the opening sentence opens with it or carries it in the parenthetical after the
article's own subject (`services/reference_identity.py`). An article that only mentions the name (a
parasite its host, a predator its prey, a genus its species) is rejected before it is cached, a
renamed taxon is recognised through the catalogue's recorded synonyms, and a cached description is
held to the same rule before it is shown. The card shows no description rather than a wrong one. The species a record is about is
named in its ladder, its tree's title and its node in every tree layout as the record's heading names it (`withRecordName` in
`taxonomy/nomenclature.ts`), so one bird has one name on one screen. Every fact has its own loading, absent and failed state; a failed one
offers Try again, and one that is not known is left out. The card stays inside the dialog its name sits in (the family
tree, a record), else the window, and never covers the name it describes: below it, else above, else
beside it on the roomier side, else on the roomier side with its own scroll (`taxonomy/card-placement.ts`).
A card that scrolls inside fades into the surface at its foot until its end, so cut-off text never
reads as the whole card. Garden animals are named as the Garden record names them: the taxonomy
routes case SpeciesNet's lowercase names with the same `vernacular_case` the Field log and Explorer
use, and scientific names are never re-cased. A pinned card takes Tab into its controls; Tab past them, or Escape, hands focus back to the
name without reopening the card. Selecting a species, which has nothing to open, pins its card; the
species details show the same ladder. The tree is a ranked classification, and the footer says so: it
shows grouping, not divergence.

### Standing (Leaderboard)

```
span and source: one compact row (on a phone the span is a select and "Include Unknown bird" is under More)
wall: the leader named, the share bar as its navigation, then a contact sheet of this feeder's own visits
flagged species: probable misidentifications, named apart for a person to check
standing band: species, visits (captures in the all-time view), busiest hour, heard or confirmed, rising, most recent
  (beside the wall in a side column from 1280 px; under it on narrower screens)
rankings (with evidence, each row with this feeder's own crop), then analytics, both at full width
```

Use of the width: from 1280 px the standing figures, which summarise rather than ask for anything,
stand in a side column beside the wall and its checks; the rankings table and the charts take the
page's full width, so a wider screen shows more of the table's columns rather than wider cells. A
ranking row's picture is this feeder's own newest crop of the species (its portrait, else its newest
visit on the wall), then the species' reference picture, and otherwise an empty slot: never a
stand-in icon. Each chart is a `ChartFigure` with one heading; the window is said once for the
section, each chart's total sits in its caption, and its data is a table that follows what the chart
draws (the visible series and any weather overlay).

A leaderboard is only as good as its identifications, so the rankings say what stands behind each
species besides the classifier: confirmed by the owner, heard by BirdNET in the same window, or the
camera alone (`leaderboard/evidence.ts`). A trend is claimed only when the history covers the whole
previous window (`previous_window_complete` from the route); otherwise the page says when records
start. Rankings count visits (`window_visit_count`, the shared server rule of a 60-second inactivity gap after the latest verified event end,
with capture time as the fallback). Only the all-time view, which has no visit counts, shows the raw total of stored
photographs, and it calls them captures ([`glossary.md`](glossary.md), Counting): a raw total is never relabelled as visits.
The Leaderboard's strings still say "detections" until its copy pass; the copy-lint baseline counts them.
The timeline and the composition chart share one colour per species
(`leaderboard/species-palette.ts`, validated for colour-blind separation on both surfaces).

The wall (`CaptureWall`) opens the page. Its header names the leading species, and under it the
share bar is the wall's navigation: one segment per species in its chart colour, sized by its share,
then the species beyond the list summed as "other species" and the flagged ones as "Needs a check"
(`SpeciesChecks`, which lists them for a person to review). For an owner it opens the check sheet
(`SpeciesCheckSheet`, decisions in `utils/species-check.ts`): one flagged species at a time, its
visits as their best crops (never the whole scene), all selected, and the likeliest answer first
with its effect on the button. Only the suggestion commits in one tap; any other species takes a
second, because a rename also teaches personalised identification and is not undone by renaming
back. On a phone the crops are a sideways strip so the answer stays within reach. Hovering or focusing a segment opens it
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

Use of the width: from 1280 px what a reader looks up rather than reads through (what it stores,
what leaves the network and the credits) stands in a side column beside the portrait, the pipeline
and this instance; below that it follows them, in the same order. The pipeline lays its steps out by
the room it is given (a container query), not by the window. "What leaves your network" lists what
is sending now (On and Always) first; everything else it can contact waits behind one disclosure,
**Show everything YA-WAMF can contact**, with a count of the rest.

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

### Health

The System card (the verdict, the host's chart and the resource table) keeps the page's full width
in every band. From 1280px what happened (`HealthActivityTimeline`) takes the main column and the
history (earlier incidents, backend warnings and errors) and the diagnostics export stand in a side
column beside it; below that they follow it, the two history lists side by side from 1024px.

## 3. Components and where they belong

| Component | Use for | Do not |
| --- | --- | --- |
| `FieldLog` | The Dashboard's chronological visit log and its identification actions | Use for operational history or search results; Health and Explorer own those |
| `HealthActivityTimeline` | The Health page's chronological account of recorded visits, expected filtering and fault drops, with each outcome stated explicitly | Turn it into an identification queue; the Dashboard owns outstanding work |
| `FieldLogVisitRow` | One visit on the field log's thread, opening from its time onto its captures in the same columns | Add a second disclosure control, or colour capture nodes without also changing their shape |
| `FieldLogGardenRow` | One Garden animal's visit on the field log's thread, in a bird visit's columns, opening the Garden record | Omit the worded **Garden** marker, or let it count towards a bird total |
| `VisitCaptures` | A visit's chronological captures: `inline` inside a Health row, `footer` closing an Explorer card or row | Render for a single capture, repeat the visit's camera or day on each line, or sum birds across captures |
| `FilteredFramePreview` | A frame the classifier rejected, which has no detection record | Use where a `Detection` exists; that is `DetectionPreview` |
| `DetectionPreview` | Any thumbnail under ~64px | Use as a click target for navigation; click opens the record |
| `GardenCapturePreview` | A Garden capture's thumbnail in the field log, the Explorer list or a Garden visit's captures | Show media the server did not list for the reader, or copy the hover handling instead of using `HoverPopout` |
| `FrameStrip` | The moments of one visit inside its record, with the comparison pop-out | Show framing variants of one moment side by side; the pop-out carries the framing |
| `ReviewQueueCard` | Outstanding decisions | Use for notifications or job progress |
| `DayBar` | The window label plus its headline metrics | Add a seventh metric; cut one instead |
| `DeskContextCards` | Standing operational context | Put actions in it |
| `TopVisitors` | A full-width band | Place it in the context rail; it lays out horizontally and compresses badly |
| `InstancePipeline` | Deployment state as a flow | Use it as a settings surface |
| `ReviewQueueModal` | Working a queue item by item | Use for viewing one record; that is `DetectionModal` |
| `ActivityHeatmap` | A weekday by hour grid that reads a slot on hover, tap or arrow keys, with hour and day totals in its margins | Rely on native `title` tooltips; they arrive late and never on touch |
| `CameraWatchRow` | One Frigate camera in **Settings → Cameras & connection → Cameras to watch**, shaped as a settings row: the camera's name and Preview on the left; "Watch for" (Off, Birds, Garden animals or Both, as one select) and, while it watches birds, its role (select) in the control column; motion photos below while it watches Garden animals | Add a second camera list for one subject elsewhere; link to this list and summarise instead |
| `BetaFeatureCard` | One feature on **Settings → Identifying birds**: name, one-line description, its switch (staged, applied with the page), a worded status line with an amber dot only when the owner must act, its settings only while on, and what off means while off | Add a feature's settings outside its card, or invent a beta feature to fill the list |
| `BetaSection` | A collapsible group of one beta feature's settings: the heading is the disclosure button, and a closed section stays mounted but hidden so a download or status read inside keeps running | Nest cards inside it; sections are separated by hairlines |

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
confidence. Camera and day stay at visit level. The camera appears beneath the species name only when the log holds more than one camera.
Primary species names wrap fully, including in narrow desktop dashboard columns; the camera
shares the metadata line so it cannot squeeze the name into a separate tiny column.
`VisitCaptureList` reads the first page when a visit first opens and reuses it until the visit,
window or access changes; Health rows and Explorer cards use the same loader through
`VisitCaptures`. Explorer grids use a native floating capture panel above the cards, so no grid row moves
when it opens. Its control works by click, touch or keyboard; Escape, an outside click or
Close dismiss it. The panel stays within the viewport and scrolls long lists. Thumbnail
previews portal into the panel's top layer. Explorer list and Health layouts stay inline. `FrameStrip` removes unwanted photo choices reversibly with Undo while retaining
counting evidence. Recent species sightings open exact detection links.

Loading never claims a state, and it never moves the page when it ends. Until the day has been
read, the field log shows as many placeholder rows as it will show, in the anatomy and height of
real rows; the day bar shows placeholders instead of zeros, in every figure it will hold, with the
note line beneath a figure that carries one; the review queue does not say "Nothing waiting"; and
the camera list does not say none are reporting. Which figures the day bar holds comes from
configuration (`dayBarSlots()` in `utils/day-bar.ts`: BirdNET on, and `bird_counting_enabled` from
the public settings), never from whether a reading has arrived. A lazy page's placeholder is a
screen tall, so the footer does not show beneath an empty page and jump when the page lands, and
the header keeps the refresh button's place (disabled) on a page that will register one. The About
portrait shows its media box and fact rows while it loads, and one quiet line if the read fails.
`browser-tests/dashboard-layout.spec.ts` and `about-portrait.spec.ts` hold cold loads to a layout
shift under 0.05 on a desktop and 0.1 on a phone, with the readings delayed. A first
read that fails says so with a retry. Every placeholder stands still under reduced motion.
The Explorer follows the same rule through one tested decision, `explorerPane()` in
`utils/explorer-results.ts`: first load, error, empty, filtered empty or results. A failed read is
never an empty state and its count reads "Count unavailable", earlier results stay dimmed under the
alert, and a refetch dims what it replaces with `aria-busy` until the new page arrives.

Pure logic lives in `apps/ui/src/lib/utils/`: `visit-grouping.ts` (summary adapters, fixture grouping, the desk window and
threshold-aware review decisions), `review-queue.ts` (queue selection and ordering),
`dashboard-cameras.ts` (configured-camera scope and visit counts), `camera-watch.ts` (each camera's
Off, Birds, Garden animals or Both choice and how it saves to the server's separate camera lists), `pipeline-health.ts` (which
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
- Stays open while the pointer travels into the panel. `DetectionPreview`, `GardenCapturePreview`
  and `FrameStrip` use a 120ms close grace window for exactly this (SC 1.4.13, "hoverable").
- Dismisses on `Escape` without moving focus elsewhere unexpectedly.
- Reuses the image already fetched. A preview must not cost a second request.
- Respects `prefers-reduced-motion`: it appears without the scale transition.
- The trigger is a real `button` with a visible focus ring.
- While open, the panel has a unique stable `id` and its trigger points at it with `aria-describedby`, so
  a screen reader reads the name, score, state and camera after the trigger's label. The attribute is
  removed when the panel closes. `HoverPopout` takes the component's `$props.id()` and supplies both.

Model any new popover on this and on `CameraStatus.svelte`, which established the pattern. A small
capture's preview takes the shared controller rather than its own copy: `HoverPopout`
(`utils/hover-popout.svelte.ts`) owns opening, the grace window, Escape, focus leaving and following
the trigger on scroll, and `HoverPopoutPanel` is the portalled panel. `DetectionPreview` and
`GardenCapturePreview` both use them.
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

- **One word for each thing.** [`glossary.md`](glossary.md) lists the term for every concept, the
  words it replaces, each language's form of address and the rules for units. `copy-lint.test.ts`
  holds every locale file to it.
- **No em dashes.** Use a comma, a colon, a semicolon or a full stop. The locale test covers all
  nine languages and `dialog-close-and-copy.layout.test.ts` covers English fallbacks in the code.
- **Sentence case.** Buttons, headings and labels capitalise their first word and names only:
  "Clear history", "Test AI connection", "Keyboard shortcuts". Names are products (Frigate,
  BirdNET-Go, eBird, iNaturalist, BirdWeather, Home Assistant, YA-WAMF), places, models, and the
  app's own pages and tabs where a sentence cites them ("Settings → Cameras & connection"). The editorial
  locale test fails a short Title Case label in English, Spanish, French, Italian, Portuguese and
  Russian; German keeps its capitalised nouns, and Japanese and Chinese have no case.
- An error states the cause and the next step. "This page stopped working … Reload the page; if it
  happens again, copy the error details into a GitHub issue", never "Something went wrong".
- A badge says something its surroundings do not. An owner-only page does not mark items "owner".
  Where it matters that visitors do not see something, the page says so once in a sentence
  ("Background jobs, health and system events are shown only to you, not to visitors."), never on
  every row.
- The footer of a working page carries the build's version, the licence and the links, and nothing
  that changes from page to page. About carries no general bird trivia either: every line on it is
  about this install.
- A count names its unit and its window: "Detections, all time", "Availability, last 24 hours".
  A figure that was not measured is said in words at body size ("Not measured. The start time could
  not be read from the backend."), never as a headline value beside one that was.
- The detection record reads, and is walked by keyboard, in one order: identification, the
  decisions about it, the facts, reference reading shortened to a few lines with a link to its
  source, then the identifiers. Nothing is re-ordered in CSS. One primary and one secondary button
  sit under the name; every other action (score again, rename, hide, delete permanently) is a row
  in the "More actions" list. A button takes its label's width so the label does not wrap.
- Status belongs in the panel, never over the photograph: only the favourite star sits on the image.
- A list whose rows lead somewhere makes the row the link, with a chevron at its right edge and the
  time on the title line. It does not add a boxed "Open" under every row.
- An identifier made of parts (`model · runtime`) breaks between its parts, never inside one.
- Name a control by its effect. "Identify", "Add House Sparrow", "Work through the queue".
- Empty states say what is true and what is next: "Every visit in the last 24 hours has a species.
  Nothing waiting on you." Never a bare "No data".
- State an unknown as unknown. Do not round it up to healthy.
- No nature-documentary register. "A camera pointed at a feeder, and a great deal of curiosity" is
  the wrong voice. "A feeder camera, a classifier, and a database" is closer; the plainest correct
  sentence is usually right.
- Identifiers are not copy. Table names, topics and model ids render as literal monospace strings
  and never go through i18n.
- Every user-facing string goes through `svelte-i18n` with a `{ default: '…' }` fallback, and lands
  in all nine locales. A key lives in the file named after its top-level domain,
  `apps/ui/src/lib/i18n/locales/<language>/<domain>.json`, so `garden.explorer.title` is in
  `locales/en/garden.json` and its eight translations. A new top-level domain is a new file in
  every language. The locale audit enforces key parity; genuine cognates and product names go in
  `locales.identical-baseline.json`. A key a translation still lacks renders in English, never as
  the raw key.
- A count chooses its word. Write `{count, plural, one {# visit} other {# visits}}`, never
  "{count} visits" or "visit(s)", and give each locale the forms it needs: Russian takes `one`,
  `few`, `many` and `other`; Japanese and Chinese take `other` alone. Pass the number, not a
  formatted string: `#` formats it in the reader's locale. `locales.plurals.test.ts` enforces this,
  and lists the few strings where `{count}` stands before a word that does not change with it.

---

## 6. Visual details worth copying

- **Type**: the display face (`font-display`) for headings and figures, the body face for
  everything else; the shipped classic pairing is Playfair Display over Source Serif 4, and the
  font setting swaps both. Figures that stand alone use `.figure` (display face, lining tabular
  digits). `tabular-nums` wherever digits align in a column. Small print uses `text-3xs` (11px)
  and `text-2xs` (12px) or `text-xs`: sizes in rem, never `text-[Npx]`, so display scaling and
  the reader's text size carry through.
  The root size grows on a large display (`100% * clamp(1, 1 + (100vw - 1280px) / 4096px, 1.25)`,
  written with `tan(atan2())` in `app.css`), so a rem layout scales as a whole and still doubles
  with the browser's text size; never set a px font size, or add a px term, on the root. The reader's
  **Text size** in Appearance multiplies it through `--text-scale` (per device, 75% to 150%, with
  Standard at 87.5%), so a layout must hold at the largest size on a 320px phone, not only at the
  default. Touch targets use the `11` spacing step, which is `max(2.75rem, 44px)`: never write a
  target size that a smaller text size could take below 44px.
- **Finish**: flat. Panels are a hairline (`line-soft`) and a fill (`surface`), with no shadow, blur
  or gradient wash; `surface-raised` fills a well inside a panel. These tokens are set per mode and
  theme in `app.css`, so a component never names a theme. Gradients remain only where they do a
  job: a scrim that keeps a caption legible over a photo, a scroll fade, a loading shimmer.
- **Labels and controls**: a small label (`.eyebrow`) names a group or a window. Like every control,
  heading and label it is in sentence case at normal tracking: it stays below its heading by size,
  weight and a muted ink, never by capitals. Nothing forces capitals with CSS
  (`dialog-close-and-copy.layout.test.ts`), so a translated label reads as written.
- **One object, one choice**: when one thing takes part in several subjects, as a camera can watch
  for birds and Garden animals, give it one row with one single-choice control that names the
  combinations (Off, Birds, Garden animals, Both). Options that belong to one subject appear under
  the row only while that subject is chosen. A choice that cannot be made is disabled, struck
  through and explained in words beside the control, never hidden.
- **Selection**: a selected route, tab or option is a recessed key in the brand tint with a lit
  icon. Never a coloured bar on one edge. A chosen row in a list of choices uses the kit's
  `.choice-active` (brand tint, medium weight, a lit check or other icon); hover stays a neutral
  wash and keyboard focus a ring, so the three never read as one. A short "choose one" (a
  settings row, the Explorer's Visitors, Show and When, its Cards/List switch) is the one
  exception, and it has one shape everywhere: the shared `Segmented` control, a neutral track with
  the chosen segment raised, set semibold and marked with a small check, no brand fill. The check
  keeps the choice readable in high contrast, where every button is painted alike. Short options
  may wrap on the track; four or more long options, or options that need a sentence each, become a
  select or a radio list instead. So the Explorer's filter rail has two selected styles, not four:
  the segmented track for short choices and `.choice-active` rows for lists.
- **Settings rows**: every Settings section (one of the six task sections in the rail) is a column of
  cards no wider than `max-w-3xl`, each former tab a part with an anchor of its own. A card is a
  plain `h2` (no icon, no coloured band) over one card of rows separated by hairlines,
  and nothing inside the card is boxed again. From 768px a row puts its label (medium weight) and
  hint (regular, muted, one size smaller) on the left and its control in a 20rem column on the
  right, so every field, select and switch ends on the card's right edge, a section's own switch
  included; on a phone the row stacks. A button that acts at once sits in its own row at its own
  width, never stretched across the card. Extra fields hide behind a plain "Show advanced options"
  disclosure at the end of the section. Settings uses the app's own fonts, like every other page.
- **Charts**: a line or bar chart takes `chart-h` or `chart-h-tall`, a height between a floor and
  a cap that follows the window width, so a wide screen neither flattens it into a strip nor
  stretches it without bound (keep it under about 4.5:1). Bars take their width from their slot
  (`barPercentage`, `categoryPercentage`) with a generous cap. A heatmap keeps square cells with a
  maximum size, so its columns fit a phone and stop growing on a wide screen.
- **Photographs in a fixed box**: fill the box (`object-cover`) unless that would cut away more
  than a quarter of the photo, as for a tall crop of a woodpecker on a pole. Then show it whole
  over a soft blurred copy of itself. `utils/photo-fit.ts` decides from the loaded image; the
  detection card and the record's photograph use it (#481).
- **Panels**: `card-base` for standing surfaces. Rows inside a list are separated by hairlines,
  not by nested cards.
- **Flagged rows**: a faint amber tint (`bg-attention-500/5`) plus an amber `.attention-dot` set
  beside the worded reason. All three, and never a bar on the row's edge.
- **Score**: a percentage in a tone band (under 60 amber, under 85 brand, from 85 green) and a
  3px bar. Never the bar alone. Take the band and its classes from `utils/score-tone.ts`
  (`scoreBand()` with `SCORE_TEXT`, `SCORE_TEXT_ON_MEDIA` and `SCORE_FILL`), never local
  thresholds: the helper bands the whole percentage a person reads, so a card, a list row, the
  record and the field log draw one score in one colour in every theme. **Exception:** a frame the filter rejected scores under 60 by
  definition and wants nothing from anyone, so it renders in slate with its reason in words. Amber
  on those rows would contradict 1.3 and put seven of them under a heading saying nothing failed.
- **One name**: a component names a bird through `$birdNames(…)` (`naming.ts`) wherever it is
  printed, a toast and an accessible name included, so the reader's naming preference and language
  hold on every surface. It is a store, so a name follows a language change at once; the pure
  `getBirdNames()` beneath it is for code outside a component, which passes the translated name in.
  Never print `display_name`: it is the stored English label. A visit without a species is
  "Unknown bird", in that casing and translated, from the same helper. The score a visit
  must reach to be named is the **naming threshold** everywhere, Settings included.
- **Clock and dates**: every time, date and hour label comes from `utils/datetime.ts`
  (`formatTime`, `formatHour` for a whole hour in a sentence or on an axis, `formatShortDay` for a
  chart or strip label), so the owner's clock and date format hold on a chart axis as they do in
  the log. Never call `toLocaleTimeString`, `toLocaleDateString` or `Intl.DateTimeFormat` for a
  time or date in a component.
- **Weather words**: a stored condition ("Rain") and a wind direction are translated through
  `utils/weather-condition.ts`; a condition outside the known vocabulary prints as stored.
- **Maps**: every map that draws OpenStreetMap tiles carries `MapCredit`, the credit its licence
  requires, in the app's own ink. A hint beside a map names only the gestures that map accepts.
- **High contrast**: one black scheme. The theme store adds `dark` whenever the mode is on, so a
  component needs no high-contrast styles of its own provided every light ink and fill has its
  `dark:` pair. `app.css` then repaints, inside its one nested `.high-contrast { … }` rule, each
  text colour family (`[class*='text-slate-']`), never
  a list of classes, and gives a chosen or primary control a yellow fill under black words.
  A filled element sets its ground and its ink together and everything inside it takes that ink;
  a disabled control gives up its fill and is grey on black inside a dashed edge. An ink a
  component cannot write as a utility is a token set per theme in `app.css` (the record's AI panel
  uses `--ai-*`), never a colour in a scoped `<style>`, which the mode cannot reach.
  `app.high-contrast.test.ts` fails a colour family the app writes and the mode does not repaint,
  a fill under white words that is neither dark enough nor named in the mode, and a literal ink in
  a component's styles; `browser-tests/high-contrast.spec.ts` measures every word at 7:1 over both
  themes, with and without the reading font, on filled and disabled controls and in the record's
  AI panel. A new ink colour family or filled control must be added to the mode in the same change.
- **Touch targets**: `min-h-11` on anything interactive, including chips and inline actions. The
  kit's `.tab-button` and `.btn-icon` carry the floor themselves, so a tab or an icon button needs
  no extra class.
- **Review overlay**: the queue pins the underlying page at its current scroll position while open and restores it on close. Its backdrop covers the viewport even when the page has scrollbars. Opening the full record releases the queue lock before the record takes its own lock; closing the record returns to the same page position.
- **Page headings**: every route has exactly one h1, and it uses the label of the route's menu
  item, so the Explorer page is titled **Explorer** and the species page **Leaderboard**. The
  sidebar wordmark is not a heading. On the Dashboard the day bar holds the h1, so the page header
  above it keeps only the owner's controls. Public visitors get the page title without those
  controls. The browser tab reads `<page> · YA-WAMF`. An address no page answers shows a
  not-found card with its own h1 and a button back to the Dashboard, never an empty page.
  `browser-tests/app-header.spec.ts` holds the shell to this.
- **Phone drawer**: closed, the sidebar is `inert`, so its controls take no tab stops behind the
  page. Open, it traps focus, starts on the current page's item, and closes on Escape with focus
  back on the menu button, which carries `aria-expanded` and `aria-controls`.
- **Toasts**: errors go into a `role="alert"` region and stay until closed; other toasts are polite
  and leave on their own, but never while pointed at or focused. An action that is saved at once
  and cannot otherwise be taken back, such as clearing the notification history, reports itself in
  a toast with **Undo** for ten seconds (`toastStore.undoable`) instead of asking first.
- **App headers**: page actions wrap onto another row when needed. The mobile wordmark yields to the app icon when space is tight; menu and theme controls keep their hit targets. Test the full App after a settled desktop-to-320px resize at 200% text, including keyboard refresh and camera disclosure.
- **Dashboard reflow**: the Dashboard fits 320px at 200% text and at the largest Text size. Its day bar
  and field log lay out by their own width in rem (container queries), not the screen's: the day
  bar's figures go from one row to three, two, then one column, and below 16rem a field log line puts
  the time beside the photo, the name, score and captures beneath it, and **Open** under the name.
  The `log-wide` and `log-narrow` Tailwind variants query the field log's container; every line,
  capture and placeholder takes its cell placement from `FIELD_LOG_CELL` in `utils/field-log.ts`, so
  captures keep sharing the visit's columns through subgrid. A page title too long for a narrow
  header steps down a size rather than breaking inside a word.
- **Text reflow**: capture detail sheets fit 320px at 200% text. Media flex items need `min-w-0` so an aspect ratio plus a minimum height cannot widen the sheet in Safari. Fact labels, technical disclosure chrome and footer controls wrap when enlarged text no longer fits; complete names remain readable and controls retain their touch-target floor. Check the actual modal in Chromium and WebKit, including a full-resolution whole-scene peek and its outline geometry.
- **Settings save bar and notifications**: both stack by their own width in rem (a container query), not the screen width, so enlarged text on a phone moves Discard changes and Save changes onto a full-width row and puts a notification's words below its icon and close button. Wider screens keep the single row. `browser-tests/settings-save-footer.spec.ts` checks 320px and 393px at 200% text, including keyboard activation of Save changes.
- **Disclosures**: a collapsible section is not required to look like every other one — a details
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
