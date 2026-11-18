- **The species picker lists each bird once.** When a visit was saved under a local name that the
  taxonomy cache could not resolve, such as "Большая синица", and the model's own label named the
  same species ("Parus major"), the picker offered both as separate rows once their scientific
  names were filled in. It now merges them after the names are filled in, keeping the row with the
  fullest taxonomy. Thanks to @darkslen1 for the fix.
