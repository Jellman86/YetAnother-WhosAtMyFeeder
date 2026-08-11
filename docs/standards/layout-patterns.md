# Layout Patterns

This is the design language the dashboard, the observation flow and the About page were rebuilt
in. It exists so the next person, or the next agent, extends those screens instead of inventing a
fourth style beside them.

It sits under [`ui-ux.md`](ui-ux.md), which remains the authority on heuristics, WCAG 2.2 AA and
Refactoring UI craft. Where this file is more specific, follow this file. Where it is silent,
follow `ui-ux.md`.

---

## 1. The rules that produced these screens

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
frame and the best score. Anything that lists detections to a person groups first.

### 1.3 Say what needs a human, and say why

Work that is waiting is first-class: the review queue is a docked card with a count, not a filter
someone has to think to apply. A flagged row states its reason in words ("Below the naming
threshold"), never by colour alone.

Amber is reserved for "this needs a person". It is not decoration and it is not a second accent.
Green means confirmed or healthy, brand blue means normal emphasis. A row is never coloured to
mean "recent" or "interesting".

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

Three shapes cover the app. Pick one; do not blend them.

### Desk (Dashboard)

```
day bar: label, 4 to 6 inline metrics, live indicator
[ primary log, 1.55fr ]        [ context rail, 0.7fr ]
                                queue card (the work)
                                standing cards (cameras, sensors, conditions)
                                reference (activity, top visitors)
```

The rail is ordered by urgency, not by data source: what needs you, then what is running, then
what is merely interesting. The primary column is one list, not a grid of cards.

### Evidence (Add observation)

```
slim bar: subject, status, escape hatch
[ media, 1.35fr ]              [ decision rail, 0.85fr ]
```

Chrome is a single row. Progress is shown, but it does not get a sidebar. The decision rail holds
candidates and the confirm action, and the confirm action names the thing it will do
("Add House Sparrow"), never "Save".

### Reference (About)

```
colophon: what this is, in plain sentences
live diagram: the standard flow, annotated with this instance's state
build detail: what to quote in an issue report
credits
```

Sections are ordered by reader: visitor, then anyone, then owner. Do not add a feature grid; the
readme and `docs/` hold the feature list.

---

## 3. Components and where they belong

| Component | Use for | Do not |
| --- | --- | --- |
| `FieldLog` | Any chronological list of visits | Use for search results; Explorer owns those |
| `DetectionPreview` | Any thumbnail under ~64px | Use as a click target for navigation; click opens the record |
| `ReviewQueueCard` | Outstanding decisions | Use for notifications or job progress |
| `DayBar` | The window label plus its headline metrics | Add a seventh metric; cut one instead |
| `DeskContextCards` | Standing operational context | Put actions in it |
| `TopVisitors` | A full-width band | Place it in the context rail; it lays out horizontally and compresses badly |
| `InstancePipeline` | Deployment state as a flow | Use it as a settings surface |

Pure logic lives in `apps/ui/src/lib/utils/`: `visit-grouping.ts` (grouping, the desk window, the
review threshold) and `review-queue.ts` (queue selection and ordering). New decision rules go
there, with unit tests, and never inside a component.

`REVIEW_CONFIDENCE_THRESHOLD` is 0.6 and matches the backend naming floor. If one moves, both move.

---

## 4. The hover pop-out contract

Any preview that opens on hover must satisfy all of this, because hover alone fails WCAG 2.2 AA:

- Opens on `mouseenter` **and** on `focusin`, so keyboards reach it.
- Stays open while the pointer travels into the panel. `DetectionPreview` uses a 120ms close grace
  window for exactly this (SC 1.4.13, "hoverable").
- Dismisses on `Escape` without moving focus elsewhere unexpectedly.
- Reuses the image already fetched. A preview must not cost a second request.
- Respects `prefers-reduced-motion`: it appears without the scale transition.
- The trigger is a real `button` with `aria-expanded` and a visible focus ring.

Model any new popover on this and on `CameraStatus.svelte`, which established the pattern.

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
- **Panels**: `card-base` for standing surfaces. Rows inside a list are separated by hairlines,
  not by nested cards.
- **Flagged rows**: a left-to-right amber wash plus a state dot plus a worded reason. All three.
- **Score**: a percentage in a tone band (under 60 amber, under 85 brand, above 85 green) and a
  3px bar. Never the bar alone.
- **Touch targets**: `min-h-11` on anything interactive, including chips and inline actions.
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
