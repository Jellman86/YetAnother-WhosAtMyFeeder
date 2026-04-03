# Detection Card Analysis Overlay Design

## Goal

Make automatic video-analysis state the dominant visual state on detection cards so no normal card chrome appears above it.

## Approach

Detection cards will expose a dedicated `analysisActive` state derived from existing reclassification progress. When active, the card enters a temporary takeover mode:

- the analysis overlay is rendered in its own highest-priority wrapper
- the usual image chrome is suppressed
- selection overlay yields to analysis state
- the card border shifts to an analysis accent so the state reads even before the overlay content is parsed

This keeps the layering contract simple: analysis is the top card state, selection is secondary, normal chrome is lowest.

## UI Contract

- While analysis is active, top badges, timestamp, play button, full-visit controls, and hover action buttons are hidden.
- The auto-analysis overlay is the only visual layer above the image/content.
- The card border temporarily switches from the normal border or selected cyan border to an analysis border treatment.
- Once analysis clears, the normal card chrome returns unchanged.

## Testing

Add source-level regression coverage in the card layout test for:

- `analysisActive` derived state
- analysis border class on the card wrapper
- analysis overlay wrapper above normal card chrome
- suppression of image chrome and selection overlay while analysis is active
