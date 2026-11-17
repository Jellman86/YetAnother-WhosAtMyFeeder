- **Pages open with a handful of files, not dozens.** A cold load used to fetch 45 to 73 separate
  script files; the app's code is now packed into a shell, one shared file and the page itself,
  so a page needs a few. The code loaded before anything is drawn is slightly smaller than before.
  Dialogs and the setup wizard keep their code apart and fetch it only when they open, and the
  charts, video player and maps still load only on the pages that draw them.
- **Pointing at a page in the sidebar starts loading it**, by mouse or keyboard, so the click that
  follows shows the page without a wait. Nothing is loaded ahead when the browser asks to save data.
