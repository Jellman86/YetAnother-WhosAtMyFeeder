- Collecting motion review photos uses much less CPU, and a restart no longer starts a long
  full-core catch-up. The Intel image now decodes the sampled frames of each motion recording
  on the Intel GPU (VA-API) with a small built-in decoder. On a 2688x1512 camera that cut
  decoding from about 1.4 to 0.5 CPU-seconds per recording, with the same detections on 20
  test recordings. Other images, and Intel hosts without `/dev/dri`, keep decoding on the CPU and
  say so in the log and in `GET /health` under `garden_motion_decode`. The image grows by about
  26 MB. After a restart, footage older than ten minutes (previously thirty) is skipped in one
  step, and one log line says how many windows were skipped. Faster catch-up is limited to 30
  scans in any ten minutes, and the worker runs at a lower scheduling priority than bird
  classification.
- Fixes motion collection retrying the same night-time recording every 30 seconds on a
  high-resolution camera. Infrared footage with keyframe pre-roll exceeded the 16 MiB download
  limit and failed as an error instead of being skipped. The limit is now 48 MiB, and a
  recording that is still too large is skipped and counted under **Collection status** as
  `size_limit`.
