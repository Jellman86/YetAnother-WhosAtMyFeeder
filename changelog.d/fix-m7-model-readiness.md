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
- For integrators: the API reference now documents how the setup state's classifier section maps
  the model's measured readiness to its status and detail code, and the OpenAPI contract declares
  the 409 that "Delete all history" answers when the confirmed count has changed.
