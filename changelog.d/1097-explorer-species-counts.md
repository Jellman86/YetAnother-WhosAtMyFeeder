- The numbers beside the Explorer's filters now count what each choice would show. Under
  **Today** the species list counts today, and switching **Show** between **Visits** and
  **Captures** switches what is counted; the list names the unit beside **All species**, and a
  screen reader hears it with each number. Cameras, **Favourites**, **Audio matches** and
  **Hidden** follow the same period and filters. Each species is counted by the same filter that
  choosing it applies, including older records and Unknown bird, and the counts are read over the
  same moments as the results, so the number beside a species is the number of results it shows. A
  list is never narrowed by its own choice, so every species stays listed while one is chosen,
  with **0** for one not seen in the period. **Hidden** lists the species and cameras only hidden
  records hold. The numbers are read after the results, so the page arrives first. While they are
  read the list says **Counting…**: under new filters, or after **Refresh options**, each number
  waits in a placeholder of the same width, and on another page of the same filters the last
  numbers stay in view until the new ones arrive. An answer for filters you have since changed is
  never shown, and a failed read says so. Counts are read again whenever the results are, from the
  history as it is, so hiding, deleting, naming or favouriting a record, or a new capture arriving,
  is counted with the next results (part of #1097).
- `GET /api/events/filters` accepts the window and filters the visit and event lists take, and a
  `unit` of `visits` or `captures`, so its counts can follow them. Without them it counts captures
  in all visible history, as before ([docs/api.md](docs/api.md)).
