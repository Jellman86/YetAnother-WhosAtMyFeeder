- **Needs your call now counts everything waiting.** It used to work from your newest 50 detections,
  so on a busy day older visits dropped out of the count and the review, and it could say nothing was
  waiting when something was. The count and the list now come from the server, through the new
  [`GET /api/events/review-queue`](docs/api.md), and cover the whole 24 hours plus every new species.
  A failed read now says so instead of quietly leaving out new species.
