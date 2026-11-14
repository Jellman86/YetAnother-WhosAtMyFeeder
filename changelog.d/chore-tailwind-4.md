- The dashboard now needs a newer browser: Chrome or Edge 111, Firefox 128, or Safari 16.4
  (iOS and iPadOS 16.4), or later. Nothing changes on screen in a supported browser. An older
  one, such as an iPad that stopped at iPadOS 15, still loads the page but draws colours, borders
  and focus rings wrongly; see [supported browsers](docs/setup/getting-started.md#supported-browsers).
  The cause is the move of the UI's styling to Tailwind CSS 4, which builds through Vite with
  its settings in `apps/ui/src/app.css` instead of `tailwind.config.js` and PostCSS. The stylesheet
  is larger as a result, 302 kB against 186 kB before (38 kB against 29 kB compressed).
