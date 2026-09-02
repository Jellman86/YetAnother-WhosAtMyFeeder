"""The Unreleased section keeps one heading per kind.

Parallel branches each append their own `### Fixed`, a rebase keeps both, and the
section grows a second copy every few merges. It was folded by hand twice in one
day before this gate existed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from docs_consistency_check import check_changelog_headings  # noqa: E402


def test_a_duplicated_heading_under_unreleased_is_an_error(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n\n- one\n\n### Added\n\n- two\n\n### Fixed\n\n- three\n",
        encoding="utf-8",
    )
    errors = check_changelog_headings(changelog)
    assert len(errors) == 1
    assert "### Fixed twice" in errors[0]
    assert "line 13" in errors[0] and "line 5" in errors[0]


def test_released_sections_are_left_alone(tmp_path: Path):
    """Published notes people have read are not rewritten to satisfy a linter."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [Unreleased]\n\n### Fixed\n\n- one\n\n## [2.9.14] - 2026-05-03\n\n### Fixed\n\n- a\n\n### Fixed\n\n- b\n",
        encoding="utf-8",
    )
    assert check_changelog_headings(changelog) == []


def test_the_shipped_changelog_passes():
    assert check_changelog_headings() == []
