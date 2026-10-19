# Leaderboard taxonomy lookup performance

## Problem and evidence

Issue #762 reports a repeatedly failing monthly species leaderboard on
`2.22.0-dev+a4ca940`. Its diagnostics recorded four of five database connections
checked out, with `get_leaderboard_portraits` holding one for 59.34 seconds.
Retained older slow-query incidents are historical evidence, not new failures.
The browser allows 15 seconds for leaderboard requests. The bundle does not
contain a database or a query trace, so it cannot establish the reporter's exact
query duration or prove this is the only contributor.

A synthetic in-memory fixture with 10,000 captures, 25 species and 2,000 taxonomy
rows reproduces a concrete bottleneck. Despite the released expression indexes,
SQLite plans `SCAN tc LEFT-JOIN` for the aggregate and visit-count queries. The
nested null-check/OR expression prevents indexed lookup. One local run took
7.027 seconds (2.274 aggregate, 4.749 visit counts).

## Requirements and implementation

1. Preserve the set and multiplicity of taxonomy matches for every capture.
2. Prefer a present scientific name, including an empty string, over display-name
   fallback exactly as before. Keep SQLite LOWER semantics.
3. Preserve canonical species/taxon namespaces, visibility, public evidence and
   visit grouping. Never rewrite detection history or taxonomy records.
4. Use the existing lowercased scientific/common-name indexes; no migration or
   cache invalidation is required.

The shared repository join now compares the taxonomy scientific name against
`COALESCE(d.scientific_name, d.display_name)`, or the common name against the
display name only when the capture's scientific name is null. These are the same
matching alternatives expressed as two indexable arms. A taxonomy row matching
both arms still joins once. Ambiguous common names retain their previous multiple
matches; this change does not resolve or silently alter that separate identity
behavior.

## Validation and second-order effects

The same synthetic query took 0.311 seconds after the change. Both joins now use
`MULTI-INDEX OR` and the scientific/common-name expression indexes. This single
local comparison is approximately 23 times faster, not a production latency
promise. Existing visit window sorts and repeated portrait/stat queries remain.

An instruction-budget regression test fails on the original implementation and
passes with indexed lookup. It checks real repository capture and visit counts,
without a wall-clock assertion. Separate cases cover scientific precedence,
null fallback, empty and unmatched names, case differences, ambiguous common
names, overlapping matches, and custom SQL aliases. Existing canonical identity,
leaderboard evidence, taxonomy filter and full backend suites guard the shared
helper's other callers.

Shorter reads should reduce pool contention for settings and ingestion. They do
not prove the separate storage-size timeout in #755 is resolved: its diagnostic
snapshot had no connections checked out. No request timeout, pool size, worker
limit, media scan, inference behavior or production data changes here.

Rollback restores the previous SQL expression; there is no schema or data rollback.
After release, a reporter retry with fresh diagnostics is needed to confirm the
large-history failure is gone. Do not qualify native inference concurrency from
this read-query fix or from #712's successful queue report.
