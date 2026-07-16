# Settings navigation simplification design

Date: 2026-07-16
Status: In progress — Settings pass complete; primary owner and guest journeys remain

## Outcome

Make Settings easier to scan without changing routes, saved configuration, or the meaning of any
control. A person running a feeder should be able to answer “where would I change this?” from the
navigation structure instead of memorising a flat list of eleven tabs.

The subject is a self-hosted bird-detection pipeline. Its Settings page has one job: help an owner
configure and operate that pipeline safely. The navigation should therefore follow the work, from
capturing an event through understanding it, operating the installation, and adapting the interface.

## Current problem

Desktop Settings presents every tab as an equally weighted pill in one wrapping row. Connection,
Detection, AI, Security, Data, Appearance, and Accessibility compete at the same level. The row
changes shape as labels translate or the viewport narrows, and the emoji-heavy treatment makes a
dense operational surface feel busier than it is.

Mobile already uses a select, but its flat option list preserves the same information-architecture
problem.

## Direction

Keep the established Blue Tit theme, application type scale, shared card surface, and focus tokens.
This is an information-architecture change, not a rebrand.

- **Palette:** existing `surface`, `slate`, `teal`, and `brand` tokens; no new one-off colours.
- **Type:** existing application sans for labels; small uppercase group labels used only as
  navigational eyebrows.
- **Layout:** four task-based groups replace one undifferentiated wrapping list.
- **Motion:** remove the pulsing active dot and icon scaling; Settings navigation should remain calm.
- **Signature:** the groups mirror the real feeder pipeline rather than generic administration
  categories.

```text
┌ Feeder pipeline ─────┬ Intelligence ───────┬ Operations ─────────┬ Interface ───────┐
│ Connection Detection│ Integrations         │ Health Security Data│ Appearance       │
│                     │ Enrichment AI Notify │ Debug                │ Accessibility    │
└─────────────────────┴──────────────────────┴─────────────────────┴───────────────────┘
```

On mobile, the same groups become labelled `optgroup` sections in the existing native select.

## Group model

- **Feeder pipeline:** Connection, Detection.
- **Intelligence & sharing:** Integrations, Enrichment, AI, Notifications.
- **Operations:** Health, Security, Data, and Debug when enabled.
- **Interface:** Appearance, Accessibility.

Notifications lives with intelligence and sharing because it is an output of the detection pipeline,
not a low-level system operation.

## First tranche

1. Group existing routes in `SettingsTabs.svelte`; do not rename or redirect them.
2. Use semantic group labels on desktop and native `optgroup` labels on mobile.
3. Replace the animated active indicator with a stable `aria-current="page"` state.
4. Add translations for the four group labels and a source-layout regression test.

## Research basis

The implementation follows primary accessibility standards and public-service design guidance:

- [WCAG 2.2 target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
  requires pointer targets to be at least 24 by 24 CSS pixels (or sufficiently spaced). YA-WAMF uses
  a more forgiving 44-pixel minimum for the Settings navigation and camera controls.
- [WCAG 2.2 focus appearance](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html)
  recommends a clearly contrasting indicator; Settings controls use an explicit two-pixel focus ring
  rather than relying on the browser's least-visible default.
- [WAI-ARIA `aria-current`](https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA26) identifies the
  current link in a set. The active Settings destination exposes `aria-current="page"` and also shows
  a checkmark, so colour is not the only state cue.
- [GOV.UK's tabs guidance](https://design-system.service.gov.uk/components/tabs/) warns against
  wrapping tab bars and requires URL/back-button behaviour. YA-WAMF keeps its route-per-section model
  but uses grouped links at desktop widths and a grouped native select on mobile.
- [HTML's button model](https://html.spec.whatwg.org/multipage/form-elements.html#the-button-element)
  does not allow interactive descendants. Camera selection, preview, role choice, and preview close
  are therefore separate native buttons rather than controls nested inside a simulated button.
- [WAI form-label guidance](https://www.w3.org/WAI/tutorials/forms/labels/) favours native labelled
  controls because they provide predictable keyboard and pointer behaviour. Existing translated
  camera action labels are retained as each control's accessible name.

The local UI/UX Pro Max audit reinforced consistent outline icons, restrained motion, semantic HTML,
and explicit loading/error feedback. Those findings were applied without adding a new icon dependency
or changing the established visual system.

## Second tranche

1. Replace emoji navigation markers with consistent inline outline SVGs.
2. Use real route links at desktop widths while intercepting only an unmodified primary click for
   SPA navigation. Modified clicks, link copying, and browser fallback remain available.
3. Increase navigation and camera action targets to 44 pixels and add explicit two-pixel focus rings.
4. Add a visible checkmark to the active navigation item so active state is not communicated by
   colour alone.
5. Split the Connection camera card's simulated button and nested controls into separate native
   selection, preview, role, and close buttons. Announce preview loading/errors and provide meaningful
   preview alternative text.
6. Add source-layout regression coverage for navigation links and camera-control semantics.

## Third tranche — Detection

The Detection tab was the clearest example of card weight obscuring task priority. It presented
model management, confidence policy, video recovery, accelerator selection, runtime diagnostics,
device benchmarking, and species exclusions as up to five peer-level cards. That made an expert
diagnostic look as routine as choosing how confident an identification should be.

The revised default surface contains two cards and three immediate concerns:

1. the active classification model, as read-only status;
2. the identification confidence threshold, as the only always-visible tuning control; and
3. species exclusions, because this is a direct owner policy rather than runtime tuning.

Everything else remains available without changing its binding or saved value:

- **Model Manager:** model download/activation, crop-detector selection, crop behavior, crop source,
  and region overrides.
- **Advanced fine tuning:** minimum confidence floor, personalised re-ranking, video recovery,
  Frigate sublabel exchange, and video worker limits.
- **Execution mode & runtime diagnostics:** provider override, execution isolation, GPU guidance,
  runtime status, raw diagnostics, and the host compatibility test.

All three expert groups start closed on each mount. Model Manager does not fetch its larger model
catalogue until its disclosure is opened. A video circuit-breaker event, provider fallback, model
configuration warning, or OpenVINO incompatibility remains visible above the disclosures so the
minimal surface never hides a state that needs attention.

The tab retains the existing Blue Tit surfaces, teal focus colour, type family, dark mode, and save
contract. Structural emoji were removed from its card headers, sub-12-pixel labels were raised to
the shared type scale, sliders and action controls gained 44-pixel interaction areas, and the shared
Advanced disclosure now uses valid button content with visible keyboard focus.

## Fourth tranche — all Settings tabs

The same hierarchy rule now applies across the remaining tabs: show the decision a feeder owner can
make now, then reveal only the controls that decision enables. Saved values and API payloads are
unchanged.

- **Security:** authentication and public-access cards always expose their enable switch; account,
  session, proxy, guest-history, and rate-limit controls render only while the feature is enabled.
- **AI:** the model enable switch is the default configuration surface. Provider credentials,
  model choice, testing, pricing, and prompt templates appear only when AI is enabled. Historical
  usage is available through a separate disclosure instead of competing with configuration.
- **Integrations and notifications:** every optional service or delivery channel is toggle-first.
  Credentials, mappings, connection tests, and channel-specific policy appear only for enabled
  services. Disabled notification cards no longer stretch to the height of an enabled neighbour.
- **Data:** retention and media-cache policy remain primary. Setup, backup, taxonomy, timezone,
  backfill, and analysis tools share one maintenance disclosure; destructive actions have a
  separate closed disclosure. Active work opens its containing disclosure automatically.
- **Connection and Appearance:** telemetry and specialist typography/colour controls move behind
  disclosures. Frigate and camera setup, theme, language, date format, and naming stay immediate.
- **Enrichment:** read-only provider status is presented as a compact divided list instead of a
  grid of cards nested inside a card.
- **Health and Debug:** Health remains a purpose-built diagnostic view rather than pretending its
  evidence is editable configuration. Debug uses the shared row/toggle primitives in one card, with
  the model-evaluation harness behind a disclosure.

Structural emoji have been removed from Settings card headers and segmented choices. Shared card
descriptions now use readable sentence case, and the audited tabs no longer use sub-12-pixel text.
Source-layout tests protect the reveal dependencies, default hierarchy, and typography contract.

## Follow-up tranches

1. Add a concise section summary and “needs attention” state where runtime evidence supports it.
2. Review save feedback and cross-tab dirty-state behaviour.
3. Review the guest surface, primary empty states, and destructive actions against the UI/UX
   standard.
4. Capture fresh, sanitised documentation screenshots only after the information architecture settles.

## Acceptance

- Existing `/settings/<tab>` deep links and browser history behaviour remain unchanged.
- All tabs remain reachable at mobile and desktop widths.
- Group labels are translated in every committed locale.
- Keyboard focus is visible, and the active tab is exposed with `aria-current="page"`.
- Detection exposes no more than two primary cards, and expert controls start closed without losing
  their current values or hiding actionable runtime warnings.
- Optional Settings features expose their enable decision before dependent credentials or tuning.
- Data maintenance and destructive actions start closed unless work is already running.
- Audited Settings tabs contain no structural card emoji or sub-12-pixel text.
- Svelte check and Settings navigation tests pass.
