- **Model evaluation reads in your language and says what each choice does.** The page was English
  only, with options named after files ("Include per-image details (results.jsonl)", "Sweep image
  providers") and "Internal Server Error" as its only error. It is now translated in all nine
  languages and built from the same panels, switches and buttons as Settings. It explains what an
  evaluation does and costs before you start one, names columns by what they measure (**First
  guess right**, **Slow photos**), shows models by the names Settings uses, and writes each
  provider result and warning in words with the next step. See
  [Model evaluation](docs/features/model-evaluation.md).
- **Checking every model states its download first.** The option downloads every model you have not
  installed; the page now says how many and how large (for example 2 models, about 1.3 GB) and asks
  you to confirm before it starts.
- **A failed read is no longer shown as "No runs yet".** Loading, empty and failed are separate
  states, a problem names its cause and the next step with **Try again**, and the page keeps its
  place while it reads. Only the files an evaluation wrote are offered for download
  (`available_artifacts` on `GET /api/diagnostics/model-eval/runs/{run_id}`), including each
  photo's result when you asked for it.
- **Model evaluation is linked from Settings → Detection → Models**, answers the header's Refresh,
  and no longer re-reads a finished evaluation every two seconds while another one runs.
