"""Changelog fragments are validated per pull request and folded once, at release.

Nearly every branch used to edit the top of `## [Unreleased]`, so parallel branches
conflicted on the same lines. Each change now adds one file under `changelog.d/`;
the release folds them into `CHANGELOG.md` in a fixed order and removes them.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from assemble_changelog import (  # noqa: E402
    Fragment,
    ReleaseError,
    check_fragments,
    fold_release,
    fragment_errors,
    main,
    read_fragments,
)

CHANGELOG = """# Changelog

Intro.

## [Unreleased]

- An entry already written straight into the changelog.

## [2.22.0] - 2026-10-11

- A released entry.
"""


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def _repo(tmp_path: Path, changelog: str = CHANGELOG, version: str = "2.23.0") -> Path:
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (tmp_path / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    return tmp_path


# Well-formed fragments


def test_a_bullet_entry_with_a_continuation_line_is_well_formed(tmp_path: Path):
    text = "- **Clearer names.** Species names are normalised\n  before they reach your history.\n"
    assert fragment_errors("812-clearer-names.md", text, root=tmp_path) == []


def test_several_bullets_in_one_fragment_are_well_formed(tmp_path: Path):
    assert fragment_errors("fix-a-b.md", "- One.\n\n- Two.\n", root=tmp_path) == []


@pytest.mark.parametrize(
    "name",
    ["Fix.md", "fix/branch.md", "-leading-dash.md", "fix.txt", "fix", "fix branch.md"],
)
def test_a_fragment_name_must_be_a_lowercase_slug_ending_in_md(name: str, tmp_path: Path):
    errors = fragment_errors(name, "- Fine.\n", root=tmp_path)
    assert len(errors) == 1
    assert name in errors[0] and "name" in errors[0]


def test_an_empty_fragment_is_rejected(tmp_path: Path):
    errors = fragment_errors("empty.md", "\n  \n", root=tmp_path)
    assert errors == ["changelog.d/empty.md is empty; describe the change as a `- ` bullet."]


def test_a_fragment_must_start_with_a_bullet(tmp_path: Path):
    errors = fragment_errors("prose.md", "Fixed the thing.\n", root=tmp_path)
    assert len(errors) == 1
    assert "must start with a `- ` bullet" in errors[0]


def test_a_fragment_may_not_carry_its_own_heading(tmp_path: Path):
    """A heading would split the release section the fragment is folded into."""
    errors = fragment_errors("heading.md", "- Entry.\n\n### Fixed\n\n- Other.\n", root=tmp_path)
    assert len(errors) == 1
    assert "line 3" in errors[0] and "heading" in errors[0]


def test_a_hash_inside_an_indented_continuation_is_not_a_heading(tmp_path: Path):
    assert fragment_errors("hash.md", "- Entry with\n  # an indented hash.\n", root=tmp_path) == []


def test_a_local_link_must_resolve_from_the_repository_root(tmp_path: Path):
    """Fragments are read in CHANGELOG.md, at the root, not from changelog.d/."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "api.md").write_text("api\n", encoding="utf-8")
    good = "- See [the API](docs/api.md#events) and [eBird](https://ebird.org).\n"
    bad = "- See [the API](../docs/api.md) and [gone](docs/missing.md).\n"

    assert fragment_errors("good.md", good, root=tmp_path) == []
    errors = fragment_errors("bad.md", bad, root=tmp_path)
    assert len(errors) == 2
    assert "../docs/api.md" in errors[0] and "docs/missing.md" in errors[1]


# Reading the directory


def test_fragments_are_read_in_file_name_order_and_the_readme_is_skipped(tmp_path: Path):
    directory = tmp_path / "changelog.d"
    directory.mkdir()
    _write(directory, "README.md", "# How to write a fragment\n")
    _write(directory, "b-second.md", "- Second.\r\n")
    _write(directory, "a-first.md", "\n- First.\n\n\n")

    assert read_fragments(directory) == [
        Fragment(name="a-first.md", text="- First."),
        Fragment(name="b-second.md", text="- Second."),
    ]


def test_a_missing_fragment_directory_has_no_fragments(tmp_path: Path):
    assert read_fragments(tmp_path / "changelog.d") == []


def test_check_reports_malformed_and_duplicated_fragments(tmp_path: Path):
    root = _repo(tmp_path)
    directory = root / "changelog.d"
    _write(directory, "one.md", "- The same entry.\n")
    _write(directory, "two.md", "- The same entry.\n")
    _write(directory, "Bad.md", "- Fine text, bad name.\n")

    errors = check_fragments(directory, root / "CHANGELOG.md", root=root)

    assert any("Bad.md" in error for error in errors)
    assert any("two.md repeats changelog.d/one.md" in error for error in errors)
    assert len(errors) == 2


def test_check_reports_a_fragment_already_written_into_the_changelog(tmp_path: Path):
    root = _repo(tmp_path)
    _write(root / "changelog.d", "again.md", "- An entry already written straight into the changelog.\n")

    errors = check_fragments(root / "changelog.d", root / "CHANGELOG.md", root=root)

    assert errors == ["changelog.d/again.md is already in CHANGELOG.md; keep only one copy."]


# Folding at release


def test_release_puts_fragments_first_then_the_existing_unreleased_entries():
    fragments = [Fragment("a.md", "- Fragment A."), Fragment("b.md", "- Fragment B,\n  two lines.")]

    folded = fold_release(CHANGELOG, fragments, version="2.23.0", date="2026-11-15")

    assert folded == (
        "# Changelog\n\nIntro.\n\n"
        "## [Unreleased]\n\n"
        "## [2.23.0] - 2026-11-15\n\n"
        "- Fragment A.\n\n"
        "- Fragment B,\n  two lines.\n\n"
        "- An entry already written straight into the changelog.\n\n"
        "## [2.22.0] - 2026-10-11\n\n"
        "- A released entry.\n"
    )


def test_release_order_does_not_depend_on_the_order_fragments_are_given():
    forwards = [Fragment("a.md", "- A."), Fragment("b.md", "- B.")]
    folded = fold_release(CHANGELOG, forwards, version="2.23.0", date="2026-11-15")
    assert fold_release(CHANGELOG, list(reversed(forwards)), version="2.23.0", date="2026-11-15") == folded


def test_release_with_only_fragments_and_an_empty_unreleased_section():
    changelog = "## [Unreleased]\n\n## [2.22.0] - 2026-10-11\n\n- Old.\n"

    folded = fold_release(changelog, [Fragment("a.md", "- New.")], version="2.23.0", date="2026-11-15")

    assert folded == "## [Unreleased]\n\n## [2.23.0] - 2026-11-15\n\n- New.\n\n## [2.22.0] - 2026-10-11\n\n- Old.\n"


def test_release_of_a_changelog_with_no_earlier_version():
    folded = fold_release("# Changelog\n\n## [Unreleased]\n", [Fragment("a.md", "- New.")], "0.1.0", "2026-11-15")
    assert folded == "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-11-15\n\n- New.\n"


@pytest.mark.parametrize(
    ("changelog", "fragments", "version", "date", "message"),
    [
        ("## [2.22.0] - 2026-10-11\n", [Fragment("a.md", "- A.")], "2.23.0", "2026-11-15", "no ## [Unreleased]"),
        ("## [Unreleased]\n\n## [2.22.0] - 2026-10-11\n", [], "2.23.0", "2026-11-15", "nothing to release"),
        (CHANGELOG, [Fragment("a.md", "- A.")], "2.22.0", "2026-11-15", "already has ## [2.22.0]"),
        (CHANGELOG, [Fragment("a.md", "- A.")], "v2.23", "2026-11-15", "not a version"),
        (CHANGELOG, [Fragment("a.md", "- A.")], "2.23.0", "15/11/2026", "not a YYYY-MM-DD date"),
    ],
)
def test_release_refuses_an_unsafe_fold(changelog, fragments, version, date, message):
    with pytest.raises(ReleaseError, match=re.escape(message)):
        fold_release(changelog, fragments, version=version, date=date)


# Command line


def test_check_command_passes_for_well_formed_fragments(tmp_path: Path, capsys):
    root = _repo(tmp_path)
    _write(root / "changelog.d", "good.md", "- Good.\n")

    assert main(["--root", str(root)]) == 0
    assert "1 changelog fragment is well formed" in capsys.readouterr().out


def test_check_command_fails_for_a_malformed_fragment(tmp_path: Path, capsys):
    root = _repo(tmp_path)
    _write(root / "changelog.d", "bad.md", "No bullet.\n")

    assert main(["--root", str(root)]) == 1
    assert "bad.md" in capsys.readouterr().out


def test_preview_prints_the_release_without_writing_anything(tmp_path: Path, capsys):
    root = _repo(tmp_path)
    fragment = _write(root / "changelog.d", "new.md", "- New.\n")

    assert main(["--root", str(root), "--preview"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("- New.\n\n- An entry already written straight into the changelog.")
    assert fragment.exists()
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == CHANGELOG


def test_release_command_writes_the_changelog_and_removes_only_fragments(tmp_path: Path):
    root = _repo(tmp_path)
    directory = root / "changelog.d"
    readme = _write(directory, "README.md", "# How to write a fragment\n")
    fragment = _write(directory, "new.md", "- New.\n")

    assert main(["--root", str(root), "--release", "2.23.0", "--date", "2026-11-15"]) == 0

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]\n\n## [2.23.0] - 2026-11-15\n\n- New.\n\n- An entry already" in changelog
    assert not fragment.exists()
    assert readme.exists()


def test_release_command_refuses_malformed_fragments_and_changes_nothing(tmp_path: Path, capsys):
    root = _repo(tmp_path)
    good = _write(root / "changelog.d", "good.md", "- Good.\n")
    _write(root / "changelog.d", "bad.md", "No bullet.\n")

    assert main(["--root", str(root), "--release", "2.23.0", "--date", "2026-11-15"]) == 1

    assert good.exists()
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == CHANGELOG
    assert "bad.md" in capsys.readouterr().out


def test_release_command_refuses_a_version_that_differs_from_the_version_file(tmp_path: Path, capsys):
    root = _repo(tmp_path, version="2.23.0")
    fragment = _write(root / "changelog.d", "new.md", "- New.\n")

    assert main(["--root", str(root), "--release", "2.24.0", "--date", "2026-11-15"]) == 1

    assert fragment.exists()
    assert "VERSION is 2.23.0" in capsys.readouterr().out


# The repository itself


def test_the_shipped_fragments_are_well_formed():
    root = Path(__file__).resolve().parents[2]
    assert check_fragments(root / "changelog.d", root / "CHANGELOG.md", root=root) == []
