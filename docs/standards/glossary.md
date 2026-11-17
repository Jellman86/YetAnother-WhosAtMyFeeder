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
is not wrong English; it is a second name for something that already has one. The "Not" columns
are exactly the words the copy lint refuses: the test fails if a word is listed here and not
enforced, or enforced and not listed here.

### What the feeder records

| Term | What it means to the owner | Not |
|---|---|---|
| **visit** | One bird coming to the feeder: everything the camera kept from its arrival until it had been gone for a minute. Visits are what the app counts, lists and ranks. | detection, detections, sighting, sightings |
| **capture** | One stored photograph from a visit, with its own time and score. A visit has one or more captures. | |
| **record** | The page of one capture: its photograph, its identification, its evidence and its actions. "Open the record." | |
| **call** | One bird heard by the microphone (BirdNET-Go). Calls are heard, visits are seen. | |
| **observation** | Something the owner adds by hand (Add observation) or chooses to send to iNaturalist. Never a camera visit. | |
| **sighting** | Someone else's report nearby, from eBird. Never this feeder's own visits. | |

**Detection is internal only.** It is the database row and the Frigate concept, and it stays in
code, logs, API fields and developer docs. In the UI it is a visit, a capture, a record or a call,
whichever the sentence is about; "audio detection" is a call. A frame is one image inside a clip,
before anything is stored, and is not a capture. "Event" is Frigate's word for what it sends: use
it only when the sentence is about Frigate ("Frigate no longer has this event").

**Counting.** Two counts exist and they are never interchanged
([`layout-patterns.md`](layout-patterns.md), Standing):

- **visits** wherever the visit rule has been applied: the Dashboard, Explorer, and the
  Leaderboard's day, week and month views;
- **captures** for a raw total of stored photographs, where no visit count exists: the
  Leaderboard's all-time view, a species' all-time total, storage and retention figures.

A raw total is never relabelled as visits, because several captures can be one visit and the
figure would overstate the birds. Where both appear together, say both: "161 captures in 123
visits".

### Naming birds

| Term | What it means to the owner | Not |
|---|---|---|
| **model** | What names the birds: the thing the owner downloads and chooses under Settings → Identifying birds. | classifier, classifiers |
| **naming threshold** | The score a guess must reach before a visit is saved under that species' name. Below it, the visit is kept as Unknown bird. | confidence threshold, species threshold, classification threshold, score threshold, configured threshold |
| **Unknown bird** | A visit the model could not name with enough confidence. Always these two words, capital U. | Unknown species, Unidentified bird, Unidentified visit |
| **bird finder** | The small model that finds where the birds are in a photograph, so each one can be cropped and named. | crop detector, crop detectors, bird detector, bird detectors, crop model, crop models |
| **score** | How sure the model was, as a percentage. "Confidence" is acceptable in a sentence ("at least 70 % sure"); the figure itself is a score. | probability, certainty |
| **AI** | The optional language-model features (AI insights). | LLM, LLMs |

A model has two names, and both come from one formatter
(`identificationModelName` and `identificationModelLabel` in
`apps/ui/src/lib/settings/identification-models.ts`): the **purpose name** an owner chooses by
("Birds of your region, quick") and the **technical name** for comparing with documentation
("Small Birds"). The model settings, the first-run wizard, Model evaluation and About all call it,
so a model is never one thing in Settings and another in its results. The catalogue's bracketed
claims ("Elite Accuracy") are never shown: a measured evaluation carries the accuracy claim.

### Places in the app

| Term | What it means to the owner | Not |
|---|---|---|
| **Explorer** | The page that lists every visit, with filters. | Go to Events, Events page, Events tab, history page |
| **Health** | The page that says whether the feeder is working and what went wrong. | system health, Errors page, Diagnostics page |
| **Needs your call** | Everything waiting for the owner to decide, of every kind: visits to confirm, rename or dismiss, the species the range check flags, Garden photos to confirm, and any later kind of waiting work. One name for the queue, the card and the state, whatever is in it. | Needs review, Awaiting review, Pending review, review queue |
| **Garden animal** | A visitor that is not a wild bird (a squirrel, a hedgehog, a kept hen), recorded by the Garden feature. | Garden wildlife, garden visitor, garden visitors, Garden creature, Garden creatures |

"Needs your call" is the name of the work, not of one list. A section inside it may say what kind
of decision it holds ("Needs a check" for flagged species), under that one name.

A path through the app is written with `→` and the names as the screen shows them:
"Settings → Identifying birds". One separator everywhere, and never a path where a link can be
offered instead.

### People

| Term | What it means | Not |
|---|---|---|
| **owner** | The person who runs this install and signs in. | admin, admins, administrator, administrators, operator, operators |
| **guest** | Anyone viewing without signing in, when public access is on. | anonymous user, anonymous users, public user, public users |

"You" is the owner. A guest is "guests" in the owner's settings and "you" on the screens a guest
sees. A "visitor" is a bird, never a person.

### Where a forbidden word stays

The glossary names the app's own things. A word from a "Not" column is left alone in three narrow
cases, each of them listed in `copy-lint.ts`:

- **Inside `<code>`.** An identifier, a setting name or a value is shown literally:
  `<code>detection</code>` is a field, not a noun the app chose.
- **Another product's name for its own feature.** Frigate's "motion detection" and "object
  detection" are what the owner will look for in Frigate, so "Enable motion detection in Frigate"
  keeps Frigate's words. The list is `THIRD_PARTY_TERMS`; a phrase is added with the product that
  owns it.
- **A model's or catalogue entry's proper name**, as the registry spells it ("Bird Crop
  Detector"). The list is `PROPER_NAMES`, and a test reads the backend registry so a new name that
  would trip the lint has to be added there.

Two terms are exempt by key: "sighting" where the string is about eBird or a place, and the
literal default user name "admin" in the sign-in placeholder.

## 2. German terms

German is a full locale, not a rendering of the English. It uses the same one-term rule, and its
"Nicht" column is enforced the same way.

| English | German | Nicht |
|---|---|---|
| visit | Besuch | Erkennung, Erkennungen, Sichtung, Sichtungen |
| capture | Aufnahme | |
| record | Eintrag | Datensatz, Datensatzes, Datensätze, Datensätzen |
| call | Ruf | Audioerkennung, Audioerkennungen |
| model | Modell | Klassifikator, Klassifikators, Klassifikatoren, Klassifizierer |
| naming threshold | Benennungsschwelle | Konfidenzschwelle, Konfidenzschwellenwert, Artschwelle, Klassifizierungsschwelle |
| Unknown bird | Unbekannter Vogel | Unbekannte Art, Unbestimmter Vogel |
| bird finder | Vogelfinder | Vogeldetektor, Zuschnittdetektor, Zuschnittmodell, Crop-Detektor |
| AI | KI | LLM, LLMs |
| Explorer | Explorer | Zu Ereignissen, Ereignisseite |
| Health | Zustand | Systemgesundheit, Systemzustand |
| Needs your call | Erfordert Ihre Entscheidung | Zu prüfen, Prüfung erforderlich, Prüfwarteschlange |
| Garden animal | Gartentier | Garten-Wildtier, Gartenbesucher |
| owner | Besitzer | Eigentümer, Eigentümers, Betreiber, Betreibers, Inhaber, Admin, Administrator |
| guest | Gast | |

"Sichtung" stays for eBird reports, as "sighting" does. A word is matched whole, so a compound that
describes the activity rather than the counted thing ("Vogelerkennung") is another word. Raw totals
are "Aufnahmen", as they are "captures" in English. "Besucher" are birds, never people.

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
  Settings → Connection." Never "Something went wrong", never an error code alone, and never the
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
| `raw-error` | An errno name (`ENOSPC`), an HTTP status line or reason phrase (`HTTP/1.1 429 Too Many Requests`), or an exception's class name (`ReferenceError: …`) shown as copy. |
| `backend-prose` | A sentence that ends by quoting a raw message (`…: {error}`, `…: {message}`). |
| `status-only` | A notification that is only a label and a state ("Health status: {status}", "Zustand: Fehler"), with each language's own state words. |
| `glossary` | A word from a "Not" or "Nicht" column above, as a whole word, outside the three cases under "Where a forbidden word stays". |
| `informal-address` | du, dein, euch and their forms in German. |
| `unit-spacing` | A number or placeholder joined to its unit by an ordinary space. |
| `missing-key` | A key English has and another language lacks. |

The lint builds its patterns from the same word lists as the tables above, and the test compares
the two in both directions: a word in a "Not" column that the lint does not refuse fails, and so
does a word the lint refuses that no "Not" column lists.

**The baseline is a ratchet.** The app did not start clean, so
`apps/ui/src/lib/i18n/copy-lint.baseline.json` records how many findings each rule has in each
`language/namespace`. A count may only fall:

- a namespace that gains a finding fails, with the offending keys named;
- a namespace that loses one fails until the baseline is lowered in the same change, by
  `npm run copy:baseline` from `apps/ui/`, which refuses to raise anything;
- CI compares the committed baseline with the target branch's, so a hand-edited rise is refused.

A rule with no entry in the baseline is absolute. The copy pass lowers the rest namespace by
namespace until the file is empty.
