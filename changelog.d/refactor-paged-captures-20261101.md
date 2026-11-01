- **Bird and Garden visit captures now page through one shared loader.** Nothing changes on
  screen. Both visit capture lists read 20 captures at a time and discard a page that
  answers after the visit, window, review or owner access changed. They now share one
  engine instead of two copies, and that engine adds owner access to every list's identity
  itself. One set of tests now covers both: first page, a repeated request, paging on,
  reset, failure versus no captures, closing, late answers and the switch from owner to
  visitor. A browser check confirms that favouriting a capture opened from its visit marks
  that capture's row.
