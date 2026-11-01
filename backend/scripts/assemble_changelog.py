#!/usr/bin/env python3
"""Validate changelog fragments, and fold them into CHANGELOG.md at release.

Each pull request adds one `changelog.d/<issue-or-branch>.md` file instead of
editing the top of `## [Unreleased]`, where parallel branches used to conflict.

    python backend/scripts/assemble_changelog.py                  # check every fragment
    python backend/scripts/assemble_changelog.py --preview        # print the next release's entries
    python backend/scripts/assemble_changelog.py --release 2.23.0 --date 2026-11-15

A release writes `## [<version>] - <date>` under an empty `## [Unreleased]`, lists
the fragments in file-name order followed by any entries already written under
Unreleased, and deletes the folded fragments. It changes nothing when any fragment
is malformed or duplicated.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRAGMENT_DIRNAME = "changelog.d"
NOT_FRAGMENTS = frozenset({"README.md"})

FRAGMENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*\.md$")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UNRELEASED_HEADING = "## [Unreleased]"


class ReleaseError(ValueError):
    """The changelog cannot be folded without losing or misplacing an entry."""


@dataclass(frozen=True)
class Fragment:
    name: str
    text: str


def normalise_fragment(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def fragment_errors(name: str, text: str, root: Path = ROOT) -> list[str]:
    """Why one fragment cannot be folded into a release section, if it cannot."""
    label = f"{FRAGMENT_DIRNAME}/{name}"
    errors: list[str] = []
    if not FRAGMENT_NAME_RE.match(name):
        errors.append(
            f"{label} has an invalid name; use lowercase letters, digits, '.', '-' or '_'"
            " ending in .md, named after the issue or branch (for example 812-clearer-names.md)."
        )

    body = normalise_fragment(text)
    if not body:
        return [*errors, f"{label} is empty; describe the change as a `- ` bullet."]
    if not body.startswith("- "):
        errors.append(f"{label} must start with a `- ` bullet, in the same voice as CHANGELOG.md entries.")

    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        if line.startswith("#"):
            errors.append(
                f"{label} line {number} is a heading; the release adds the version heading, so use bullets only."
            )

    resolved_root = root.resolve()
    for match in LINK_RE.finditer(body):
        link = match.group(1).strip()
        if link.startswith(("http://", "https://", "#", "mailto:")):
            continue
        relative = link.split("#", 1)[0]
        if not relative:
            continue
        # The entry is read in CHANGELOG.md, so links are relative to the repository root.
        target = (resolved_root / relative).resolve()
        if not target.is_relative_to(resolved_root) or not target.exists():
            errors.append(f"{label} links to {link}, which does not exist relative to the repository root.")
    return errors


def _fragment_paths(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.name not in NOT_FRAGMENTS and not path.name.startswith(".")
    )


def read_fragments(directory: Path) -> list[Fragment]:
    return [
        Fragment(name=path.name, text=normalise_fragment(path.read_text(encoding="utf-8")))
        for path in _fragment_paths(directory)
    ]


def _unreleased_bounds(lines: Sequence[str]) -> tuple[int, int]:
    """Index of the Unreleased heading and of the heading that ends its section."""
    start = next((i for i, line in enumerate(lines) if line.rstrip() == UNRELEASED_HEADING), None)
    if start is None:
        raise ReleaseError(f"CHANGELOG.md has no {UNRELEASED_HEADING} heading to release from.")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def unreleased_entries(changelog: str) -> str:
    lines = changelog.splitlines(keepends=True)
    start, end = _unreleased_bounds(lines)
    return "".join(lines[start + 1 : end]).strip()


def check_fragments(directory: Path, changelog: Path, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        written = unreleased_entries(changelog.read_text(encoding="utf-8")) if changelog.exists() else ""
    except ReleaseError:
        written = ""
    first_with_text: dict[str, str] = {}
    for path in _fragment_paths(directory):
        raw = path.read_text(encoding="utf-8")
        errors.extend(fragment_errors(path.name, raw, root=root))
        body = normalise_fragment(raw)
        if not body:
            continue
        label = f"{FRAGMENT_DIRNAME}/{path.name}"
        if body in first_with_text:
            errors.append(f"{label} repeats {FRAGMENT_DIRNAME}/{first_with_text[body]}; keep only one copy.")
            continue
        first_with_text[body] = path.name
        if f"\n{body}\n" in f"\n{written}\n":
            errors.append(f"{label} is already in CHANGELOG.md; keep only one copy.")
    return errors


def release_entries(changelog: str, fragments: Sequence[Fragment]) -> list[str]:
    """Fragments in file-name order, then entries written directly under Unreleased."""
    entries = [fragment.text for fragment in sorted(fragments, key=lambda fragment: fragment.name)]
    written = unreleased_entries(changelog)
    if written:
        entries.append(written)
    return entries


def fold_release(changelog: str, fragments: Sequence[Fragment], version: str, date: str) -> str:
    if not VERSION_RE.match(version):
        raise ReleaseError(f"{version!r} is not a version such as 2.23.0.")
    if not DATE_RE.match(date):
        raise ReleaseError(f"{date!r} is not a YYYY-MM-DD date.")
    try:
        dt.date.fromisoformat(date)
    except ValueError as error:
        raise ReleaseError(f"{date!r} is not a YYYY-MM-DD date.") from error

    lines = changelog.splitlines(keepends=True)
    start, end = _unreleased_bounds(lines)
    heading = f"## [{version}]"
    if any(line.startswith(f"{heading} ") or line.rstrip() == heading for line in lines):
        raise ReleaseError(f"CHANGELOG.md already has {heading}; choose the next version.")
    entries = release_entries(changelog, fragments)
    if not entries:
        raise ReleaseError("There is nothing to release: no fragments and no entries under Unreleased.")

    head = "".join(lines[: start + 1])
    if not head.endswith("\n"):
        head += "\n"
    section = f"\n{heading} - {date}\n\n" + "\n\n".join(entries) + "\n"
    tail = "".join(lines[end:])
    return head + section + (f"\n{tail}" if tail else "")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="print the next release's entries; write nothing")
    mode.add_argument("--release", metavar="VERSION", help="fold fragments under this version and delete them")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="release date (default: today)")
    args = parser.parse_args(argv)

    root: Path = args.root
    directory = root / FRAGMENT_DIRNAME
    changelog_path = root / "CHANGELOG.md"

    errors = check_fragments(directory, changelog_path, root=root)
    if errors:
        print("Changelog fragment check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    fragments = read_fragments(directory)
    changelog = changelog_path.read_text(encoding="utf-8")

    if args.preview:
        try:
            print("\n\n".join(release_entries(changelog, fragments)))
        except ReleaseError as error:
            print(error)
            return 1
        return 0

    if args.release:
        version_file = root / "VERSION"
        recorded = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else None
        if recorded != args.release:
            print(f"VERSION is {recorded}; bump it to {args.release} before folding the changelog.")
            return 1
        try:
            folded = fold_release(changelog, fragments, version=args.release, date=args.date)
        except ReleaseError as error:
            print(error)
            return 1
        changelog_path.write_text(folded, encoding="utf-8")
        for path in _fragment_paths(directory):
            path.unlink()
        print(f"Folded {len(fragments)} fragment(s) into CHANGELOG.md under ## [{args.release}] - {args.date}.")
        return 0

    count = len(fragments)
    noun = "fragment is" if count == 1 else "fragments are"
    print(f"{count} changelog {noun} well formed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
