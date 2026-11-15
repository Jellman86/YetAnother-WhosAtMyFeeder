- **The Explorer no longer jumps as it loads.** The count ("763 visits", plus Garden and
  heard-call figures) arrives after the page is drawn, and on a desktop it shared a row with the
  search and the controls: once it was measured the controls no longer fitted beside the search,
  wrapped beneath it, and pushed the filters and every card down. The count now has a line of
  its own under the search, the loading placeholders are replaced whole rather than pushed, and
  cards take their place without fading in. Measured cumulative layout shift on a 1440 px cold
  load falls from 0.21 to about 0.01, and a browser test holds it under 0.02 at 1440 px and
  390 px.
- **Fewer controls stand between the Explorer's title and the first photo.** **Audio history** is
  now in the sidebar under **Observe** (while BirdNET-Go is connected) instead of being a second
  audio button beside **Heard calls**. On a phone **Cards**/**List** sit beside **Filters**, and
  **Heard calls** and **Multi-select** open with the filters under **View**; the selection bar
  has **Done** to leave selecting. **Days on this page** appears only when a page spans more than
  one day, and each day is its name and a plain count. The count leaves out a figure that would
  be zero, so "0 Garden visits on this page" is gone. The **Visitors** switch is three equal
  segments, one to a line. Cards no longer repeat the weather, which the record states.
- **The phone's Filters panel is a proper sheet.** It opens over the page with keyboard focus
  inside and kept inside, closes with **Close**, Escape or a tap outside, and puts focus back on
  the **Filters** button. Filters still apply as you choose them.
- **Badges are named by the words they show.** A time, a confidence or "matching call" on an
  Explorer card or row, in the field log and in a visit's captures, was announced by its
  explanation instead of its visible text, so speech input could not activate it by what is on
  screen. The words are now the name and the explanation is the description. Card text is at full
  contrast from the moment a card appears, and the background-work banner is a named region.
