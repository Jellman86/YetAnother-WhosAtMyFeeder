# Glossary and voice

One word for each thing, in every screen and every language. This page is the list. When a string
needs a noun for something on this list, it uses the term here and none of the words beside it.

[`CLAUDE.md`](../../CLAUDE.md) §5 carries the rule (plain language, actions labelled by their
effect, errors with a cause and a next step). [`layout-patterns.md`](layout-patterns.md) carries
the writing rules for sentences, plurals and locale files. This page carries the vocabulary, and
[the copy lint](#the-copy-lint) holds the app to it.

The reader is the **owner**: someone who put a camera on a bird feeder. They know birds and their
garden. They do not know Frigate's internals, model architectures or this codebase, and they should
not need to.

## 1. Terms

Each term says what it means to the owner, then the words it replaces. A word in the "Not" column
is not wrong English; it is a second name for something that already has one.

### What the feeder records

| Term | What it means to the owner | Not |
|---|---|---|
| **visit** | One bird coming to the feeder: everything the camera kept from its arrival until it had been gone for a minute. Visits are what the app counts, lists and ranks. | detection, detections, sighting, sightings |
| **capture** | One stored photograph from a visit, with its own time and score. A visit has one or more captures. | detection, frame (a frame is one image inside a clip, before anything is stored) |
| **record** | The page of one capture: its photograph, its identification, its evidence and its actions. "Open the record." | detection, entry, event |
| **call** | One bird heard by the microphone (BirdNET-Go). Calls are heard, visits are seen. | audio detection, detection |
| **observation** | Something the owner adds by hand (Add observation) or chooses to send to iNaturalist. Never a camera visit. | |
| **sighting** | Someone else's report nearby, from eBird. Never this feeder's own visits. | |
| **detection** | Internal only. It is the database row and the Frigate concept, and it stays in code, logs, API fields and developer docs. In the UI it is a visit, a capture, a record or a call, whichever the sentence is about. | |
| **event** | Frigate's word for what it sends. Use it only when the sentence is about Frigate ("Frigate no longer has this event"). | |

### Naming birds

| Term | What it means to the owner | Not |
|---|---|---|
| **model** | What names the birds: the thing the owner downloads and chooses under Settings › Models. | classifier, classifiers, network, LLM |
| **naming threshold** | The score a guess must reach before a visit is saved under that species' name. Below it, the visit is kept as Unknown bird. | confidence threshold, species threshold, classification threshold, score threshold, configured threshold |
| **Unknown bird** | A visit the model could not name with enough confidence. Always these two words, capital U. | Unknown species, Unidentified bird, Unidentified detection, Unidentified visit |
| **bird finder** | The small model that finds where the birds are in a photograph, so each one can be cropped and named. | crop detector, bird detector, crop model, bird crop detector |
| **score** | How sure the model was, as a percentage. "Confidence" is acceptable in a sentence ("at least 70 % sure"); the figure itself is a score. | probability, certainty |
| **AI** | The optional language-model features (AI insights). | LLM |

A model has two names, and both come from one formatter
(`identificationModelName` and `identificationModelLabel` in
`apps/ui/src/lib/settings/identification-models.ts`): the **purpose name** an owner chooses by
("Birds of your region, quick") and the **technical name** for comparing with documentation
("Small Birds"). Models, the first-run wizard, Model evaluation and About all call it, so a model is
never one thing in Settings and another in its results. The catalogue's bracketed claims ("Elite
Accuracy") are never shown: a measured evaluation carries the accuracy claim.

### Places in the app

| Term | What it means to the owner | Not |
|---|---|---|
| **Explorer** | The page that lists every visit, with filters. | Events, Go to Events, Events page, history page |
| **Health** | The page that says whether the feeder is working and what went wrong. | system health, Errors page, Diagnostics page |
| **Needs your call** | The visits waiting for the owner to decide: confirm, rename or dismiss. One name for the queue, the card and the state. | Needs review, Awaiting review, Pending review, review queue |
| **Garden animal** | A visitor that is not a wild bird (a squirrel, a hedgehog, a kept hen), recorded by the Garden feature. | Garden wildlife, garden visitor, Garden creature |

A path through the app is written with `›` and the names as the screen shows them:
"Settings › Models". Not `→`, not `>`, and never a path where a link can be offered instead.

### People

| Term | What it means | Not |
|---|---|---|
| **owner** | The person who runs this install and signs in. | admin, administrator, operator, user |
| **guest** | Anyone viewing without signing in, when public access is on. | visitor (visitors are birds), anonymous user, public user |

"You" is the owner. A guest is "guests" in the owner's settings and "you" on the screens a guest
sees.

## 2. German terms

German is a full locale, not a rendering of the English. It uses the same one-term rule.

| English | German | Nicht |
|---|---|---|
| visit | Besuch | Erkennung, Erkennungen, Sichtung, Sichtungen |
| capture | Aufnahme | Erkennung |
| record | Eintrag | Datensatz |
| call | Ruf | Audioerkennung |
| model | Modell | Klassifikator, Klassifizierer |
| naming threshold | Benennungsschwelle | Konfidenzschwelle, Konfidenzschwellenwert, Artschwelle, Klassifizierungsschwelle |
| Unknown bird | Unbekannter Vogel | Unbekannte Art, Unbestimmter Vogel, Unbestimmte Erkennung |
| bird finder | Vogelfinder | Vogeldetektor, Zuschnittdetektor, Zuschnittmodell, Crop-Detektor |
| AI | KI | LLM |
| Explorer | Explorer | Ereignisse, Zu Ereignissen |
| Health | Zustand | Systemgesundheit, Systemzustand |
| Needs your call | Erfordert Ihre Entscheidung | Zu prüfen, Prüfung erforderlich, Prüfwarteschlange |
| Garden animal | Gartentier | Garten-Wildtier, Gartenbesucher |
| owner | Besitzer | Eigentümer, Betreiber, Inhaber, Admin, Administrator |
| guest | Gast | Besucher (Besucher sind Vögel) |

"Sichtung" stays for eBird reports, as "sighting" does. Compounds that describe the activity rather
than the counted thing ("Vogelerkennung") are fine.

## 3. Form of address

One form per language, in every string.

| Language | Form | State |
|---|---|---|
| English | "you" | |
| German | formal **Sie**, never du, dein or euch | Enforced by the lint |
| French | vous | Already consistent |
| Portuguese | você | Already consistent |
| Russian | вы, lower case | Already consistent |
| Japanese | polite です/ます, requests with ください | Already consistent |
| Spanish | tú | Mixed today; corrected as each namespace is revised |
| Italian | tu | Mixed today; corrected as each namespace is revised |
| Chinese | 你 | Mixed with 您 today; corrected as each namespace is revised |

## 4. Sentences

- **Purpose first.** Say what the thing does for the owner, then how. "Names the birds your camera
  sees", not "Runs ONNX inference on Frigate snapshots".
- **Label an action by its effect.** "Download and set up", "Hide from history", "Delete 931 visits".
  Not "OK", "Submit" or "Apply".
- **An error gives a cause and a next step.** "Frigate did not answer. Check its address in
  Settings › Connection." Never "Something went wrong", never an error code alone, and never the
  server's or the browser's own sentence. What the server said belongs in a details disclosure,
  quoted as it arrived, under copy that was written for the owner.
- **A status is not a message.** "Health status: degraded" tells the owner nothing they can act on.
  Say what is affected and what to do: "Frigate has not answered since 08:14. New visits are not
  being recorded."
- **Only what was measured.** No reassurance the app cannot back ("Your data is safe"), no
  superlatives, no filler subtitle that repeats the page title.
- **No em dashes.** A comma, a colon, a semicolon or a full stop.
- **Sentence case** for every label, heading and button.

## 5. Dates, times, numbers and units

- **Dates and times come only from the helpers** in `apps/ui/src/lib/utils/datetime.ts`
  (`formatDate`, `formatDay`, `formatShortDay`, `formatCalendarDay`, `formatDateTime`, `formatTime`,
  `formatHour`). They follow the owner's chosen date and clock format. No `toLocaleString` in a
  component, no date written into a locale string, and no seconds unless the second matters.
- **A count chooses its word** with an ICU plural (`layout-patterns.md`, Writing). The number is
  passed as a number, so it is formatted for the reader's language.
- **Every number the owner reads has its unit**, joined to it with a no-break space (U+00A0) so the
  two never split across lines: `955 MB`, `120 ms`, `8 lx`, `{size} GB`. A percentage in running
  English text is closed up (`70%`); French and German place a no-break space before `%`.
- **One unit per quantity.** Memory and disk in MB below 1 GB and GB above; time per photo in ms;
  distances and temperatures in the owner's chosen units.

## The copy lint

`apps/ui/src/lib/i18n/copy-lint.ts` reads every string in every locale file, and
`copy-lint.test.ts` runs it inside `npm test`, so CI enforces it. It fails on:

| Rule | What it finds |
|---|---|
| `em-dash` | An em dash used as punctuation. |
| `vague-error` | "Something went wrong", "An error occurred", "Unknown error", "try again later", and each language's equivalents. |
| `raw-error` | An errno name, an HTTP status line or a JavaScript exception name shown as copy. |
| `backend-prose` | A sentence that ends by quoting a raw message (`…: {error}`, `…: {message}`). |
| `status-only` | A notification that is only a label and a state ("Health status: {status}"). |
| `glossary` | A word from a "Not" column above, in English or German. |
| `informal-address` | du, dein, euch and their forms in German. |
| `unit-spacing` | A number or placeholder joined to its unit by an ordinary space. |
| `missing-key` | A key English has and another language lacks. |

The lint and this page list the same words; the test fails if they drift apart. A word that means
something else in a few places (a "sighting" in eBird copy, the literal default user name "admin")
is exempted in `copy-lint.ts` by key, with its reason.

**The baseline is a ratchet.** The app did not start clean, so
`apps/ui/src/lib/i18n/copy-lint.baseline.json` records how many findings each rule has in each
`language/namespace`. A count may only fall:

- a namespace that gains a finding fails, with the offending keys named;
- a namespace that loses one fails until the baseline is lowered in the same change, by
  `npm run copy:baseline` from `apps/ui/`, which refuses to raise anything;
- CI compares the committed baseline with the target branch's, so a hand-edited rise is refused.

A rule with no entry in the baseline is absolute. The copy pass lowers the rest namespace by
namespace until the file is empty.
