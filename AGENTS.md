# Agent instructions

The engineering standards for this repository live in [`CLAUDE.md`](CLAUDE.md)
and apply to every contributor and every AI agent, regardless of tool.

Read `CLAUDE.md` before making changes. In short: **safety and data integrity
first, test-driven development, migrations-only databases that stay idempotent
and reversible, self-documenting code, and a clean, honest operational UI.** A
change is not done until the §6 "Definition of done" checklist passes.

User-facing documentation follows
[`docs/documentation-standard.md`](docs/documentation-standard.md). The current
assessment of the project against the standards, and the path to close remaining
gaps, is in
[`docs/reviews/2026-07-07-project-quality-and-gold-standard-review.md`](docs/reviews/2026-07-07-project-quality-and-gold-standard-review.md).

Everyday work happens on `dev`. Follow the commit rules in `CLAUDE.md` §10.

Release notes follow the human-first standard in
[`docs/development/releasing.md`](docs/development/releasing.md) and use
[`.github/RELEASE_NOTES_TEMPLATE.md`](.github/RELEASE_NOTES_TEMPLATE.md).
