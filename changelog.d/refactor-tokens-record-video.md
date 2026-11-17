- The detection record, its video player and its family tree now share one dialog header: the
  name on the left, the same round close button on the right. The family tree's "Close" text
  button is gone, its Tree, Fan and Outline switch is the same choose-one control used elsewhere,
  and the video player no longer shows a "Playing" chip beside the player's own controls.
- On a phone, a record whose photograph cannot be scanned for more birds (no whole frame kept, no
  crop detector, or another frame already being scanned or reviewed) no longer puts that notice
  between the photograph and the identification. **Find more birds** waits in **More actions**
  with its reason, and the reason is said once after the identification, where a screen reader
  hears it too, so the identification comes straight after the photograph. A frame that changed
  during a scan still says so under the photograph.
- An AI note that failed, or was still being written, no longer stays on a record after you choose
  a different species: the record offers a fresh analysis of the bird it now names.
- Figures keep their units on the same line ("6 km/h", "471 lx"), and the Conditions row on a
  phone reads as a column under its label instead of a ragged right edge.
- The photo strip's count and hint wrap onto a second line at large text sizes instead of being
  cut off, and "Choosing one changes the photograph" only appears when there is a photograph to
  choose.
- The record's lower sections read as plain rows rather than boxes inside the panel: the "how
  this was identified" note, nearby eBird sightings, every call heard around the visit (now
  behind the same disclosure as the rest of the app) and the iNaturalist draft. Small grey words
  on photographs and the video player are a step brighter.
- Under the hood, the record, the player, the photo strip, the counted-bird outlines and the
  scan controls draw from the semantic colour tokens in every mode and high contrast, the record
  dialog is split into focused parts, and the record's score bars are now part of the rendered
  contrast check in every colour theme and high contrast.
