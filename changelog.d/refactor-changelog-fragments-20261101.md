- **Changelog entries no longer conflict between pull requests.** Each change now adds
  one small file under `changelog.d/` instead of editing the top of **Unreleased** in
  `CHANGELOG.md`, where parallel branches kept colliding. CI checks every fragment is a
  well-formed bullet with no heading, broken link or duplicate.
  `backend/scripts/assemble_changelog.py --release <version>` folds them under the new
  version heading at release, in file-name order, and deletes them; entries already
  under **Unreleased** stay where they are and follow the fragments.
