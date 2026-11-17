- Model evaluation now names each model the way Settings › Models does: what it is for ("Birds
  and wildlife, high accuracy") with its technical name beneath ("ConvNeXt Large"), instead of the
  catalogue's own name and its bracketed claim ("Elite Accuracy"). About's pipeline names the
  running model the same way.
- Under the hood, a glossary ([docs/standards/glossary.md](docs/standards/glossary.md)) now fixes
  one word for each thing the app talks about (a visit, a capture, a record, the naming threshold,
  Unknown bird, Health, Explorer and more), one form of address per language and the rules for
  units. A copy lint in the test suite counts every string that breaks it, in all nine languages,
  and that count may only fall. No wording changes yet beyond the model names; the copy pass
  follows namespace by namespace.
