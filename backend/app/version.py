"""What a build calls itself. The bundle applies the same rule in
`apps/ui/src/lib/app/app-version.ts`; a contract test keeps the two channel lists identical."""

import re

# Channels whose builds are the release itself; their label never appears in the version.
RELEASE_LIKE_CHANNELS = ("main", "stable", "unknown")

_TAG_NAME = re.compile(r"v\d+\.\d+\.\d+(?:\.\d+)?")


def is_release_like_channel(branch: str | None) -> bool:
    name = (branch or "").strip()
    return name == "" or name in RELEASE_LIKE_CHANNELS or bool(_TAG_NAME.fullmatch(name))


def normalize_app_branch(branch: str | None) -> str:
    """A tag name is a release, not a branch."""
    name = (branch or "").strip() or "unknown"
    return "main" if _TAG_NAME.fullmatch(name) else name


def compose_app_version(base: str, branch: str | None, git_hash: str) -> str:
    """`base-branch+hash`, with the branch omitted for release-like channels."""
    if is_release_like_channel(branch):
        return f"{base}+{git_hash}"
    return f"{base}-{branch}+{git_hash}"
