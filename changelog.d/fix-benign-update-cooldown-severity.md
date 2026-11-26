- Health no longer turns **Degraded** when YA-WAMF pauses a Frigate update retry to avoid repeating
  work. A paused retry, a follow-up to an event Frigate called a false positive, and a nest-mode
  repeat never cost a visit by themselves, so they no longer count as issues in the sidebar. They
  stay visible: the **Pipeline** card lists them under **Skipped on purpose**, and **What happened**
  shows them as **Skipped on purpose** instead of **Fault**. A visit that is still lost after a
  paused retry is recorded as its own fault, as before. See
  [Work skipped on purpose](docs/troubleshooting/diagnostics.md#work-skipped-on-purpose).
