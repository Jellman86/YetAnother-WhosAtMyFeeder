- **The status beside each Settings section explains itself.** Each chip says what the part is for
  and its cause in words, saying only what was measured ("Frigate answers, and no camera is
  reported offline"), instead of a code in a tooltip. A reading that is out of date shows no
  causes.
- **Test results are honest about not being kept.** Frigate, MQTT, BirdNET-Go and Alerts show
  their test's result, with its time, only when it ran during this visit. Otherwise the column
  says "Test results aren't kept. Run the test to check now." and offers the test. A test run with
  values not saved yet says so, and the result goes at the next edit, Discard or Save.
