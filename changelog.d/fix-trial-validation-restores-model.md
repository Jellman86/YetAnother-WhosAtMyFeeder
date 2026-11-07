- **Validating a model no longer switches to it on a new install.** Until a model had been chosen,
  the previous selection could not be put back after a validation, so the model being checked became
  the live one, stayed live after a restart, and the setup summary kept naming the old one.
  Validating now always returns to what was running, in the setup wizard, Model Manager and
  Model Evaluation.
