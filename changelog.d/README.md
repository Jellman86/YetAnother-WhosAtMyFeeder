# Changelog fragments

Each pull request that changes behaviour, settings, an endpoint or a UI label adds
one file here instead of editing `## [Unreleased]` in [`CHANGELOG.md`](../CHANGELOG.md).
Parallel branches then add different files, so they no longer conflict on the
same lines.

- **Name** the file after the issue or branch, in lowercase letters, digits, `.`,
  `-` or `_`, ending in `.md`: `812-clearer-species-names.md`, or
  `fix-garden-motion-preroll.md` for the branch `fix/garden-motion-preroll`.
- **Write** one or more `- ` bullets in the same voice as today's changelog
  entries: lead with what someone at their feeder will notice, then the detail.
  Indent continuation lines by two spaces. Do not add headings; the release adds
  the version heading.
- **Link** relative to the repository root (`docs/api.md`, not `../docs/api.md`),
  because the entry is read in `CHANGELOG.md`.

Check fragments locally with:

```bash
python backend/scripts/assemble_changelog.py            # also run by docs_consistency_check.py in CI
python backend/scripts/assemble_changelog.py --preview  # print the next release's entries
```

At release, `--release <version>` folds the fragments, in file-name order, under the
new version heading and deletes them. See
[the release workflow](../docs/development/releasing.md#fold-the-changelog).
