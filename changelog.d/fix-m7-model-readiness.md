- A model's state is said in the same words everywhere: **Needs a download**, **Downloading**,
  **Being checked on this hardware**, **Loading**, **Ready**, **Running** or **Could not load**.
  Settings → Models, the setup wizard's review, About and Garden records all take it from one
  rule, so they can no longer contradict each other. A model that is still loading is not called
  running, and when the classifier's report gives no evidence either way the state reads
  **Not reported** rather than a guess.
- While the chosen identification model needs a download or a recovery, that is the only primary
  button on Settings → Models. The recommended model's button is secondary and says what it does
  ("Download and switch to this model").
- A Garden capture that is waiting says why when the automatic check model cannot run ("the
  automatic check model is not downloaded, so nothing can identify this yet") and links straight
  to its setup, instead of "Waiting for automatic identification" with no cause.
- Settings → Models no longer says "In use now" of a model that failed to load or is still
  loading: it says "Chosen" with the model's real state, and gives a failed model one primary way
  back, "Check and load again", including the bundled model.
- A download or hardware check started on one page shows on the others while it runs, and a model
  being checked is no longer described as downloading.
- About's pipeline states the model in the same words as everywhere else, and reports failing
  inferences on their own line instead of replacing the model's state with "Check".
- The setup wizard's review says "Not reported" when the classifier answers without saying
  whether the model is working, instead of "Chosen" or a stale "Running".
- A waiting Garden capture names what is really blocking its automatic check. Missing species data
  or a stopped Garden worker is no longer described as a model that could not load, and no longer
  points at model setup. Manual override and dismissal stay closed, with the reason, until the
  automatic check can run.
- For integrators: the API reference now documents how the setup state's classifier section maps
  the model's measured readiness to its status and detail code, and the OpenAPI contract declares
  the 409 that "Delete all history" answers when the confirmed count has changed.
