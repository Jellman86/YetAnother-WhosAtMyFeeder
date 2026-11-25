- The Explorer has an **Owner confirmed** choice under **Only**, for owners (#1099). It shows the
  visits and captures where an owner named the species: a species pick, a confirmed upload or a
  requested video reclassification. A visit counts when any of its captures was named, which is
  what its Owner confirmed badge already says, so Favourites and Owner confirmed together find a
  visit whose favourite is one capture and whose confirmation is another. Captures tagged Unknown
  Bird confirm nothing. The choice is kept in the address as `confirmed=1` for the owner only;
  visitors never see it and a link that names it shows them the ordinary view. Heard calls and
  Garden captures step aside while it is on, and the page says so. See
  [the API reference](docs/api.md).
- A visit whose photo shows Unknown Bird now wears its Owner confirmed badge when another of its
  captures was confirmed, and the badge's hint says the confirmed capture may not be the one
  shown. With a filter on in Captures, changing a capture (a new species, a favourite) reads the
  list and its count again, so a capture that no longer matches leaves the page.
