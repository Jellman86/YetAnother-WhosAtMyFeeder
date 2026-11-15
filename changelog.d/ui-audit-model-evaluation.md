- **Model evaluation reads in your language and says what each choice does.** The page was English
  only, with options named after files ("Include per-image details (results.jsonl)", "Sweep image
  providers") and "Internal Server Error" as its only error. It is now translated in all nine
  languages and built from the same panels, switches and buttons as Settings. It explains what an
  evaluation does in one sentence, with the detail behind **How this works**, names columns by what
  they measure (**First guess right**, **Slow photos**), shows models by the names Settings uses,
  and writes each provider result and warning in words with the next step. See
  [Model evaluation](docs/features/model-evaluation.md).
- **Checking every model states its download first.** The option downloads every model you have not
  installed; the page now says how many and how large (for example 2 models, about 1.3 GB) and asks
  you to confirm before it starts. A model with no known size is counted apart from the total
  instead of adding nothing to it, and the page says the download may take a while and that the
  models stay on disk until you delete their files in Settings → Detection → Models.
- **A stopped evaluation says why, and what to do.** Model evaluation, the setup wizard and the
  Detection check showed whatever the server had raised. A run now records a reason code
  (`error_code`: no installed model, no test photos, a failed request, and so on), each shown as a
  cause and a next step; the exception itself stays in the server log and is no longer written to
  the run's summary or answered by the API. The run and list answers have a declared shape
  (`ModelEvalRunResponse`, `ModelEvalListResponse`), see [the API reference](docs/api.md).
- **A failed read is no longer shown as "No runs yet".** Loading, empty and failed are separate
  states, a problem names its cause and the next step with **Try again**, and the page keeps its
  place while it reads. Only the files an evaluation wrote are offered for download
  (`available_artifacts` on `GET /api/diagnostics/model-eval/runs/{run_id}`), including each
  photo's result when you asked for it.
- **Model evaluation is linked from Settings → Detection → Models**, answers the header's Refresh,
  and no longer re-reads a finished evaluation every two seconds while another one runs.
