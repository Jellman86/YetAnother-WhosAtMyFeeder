"""Reject mutable third-party action references in GitHub workflows."""

import argparse
from pathlib import Path
import re


USES = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^\s'\"#]+)")
REMOTE_PIN = re.compile(r"[^@\s]+@[0-9a-fA-F]{40}")
CONTAINER_PIN = re.compile(r"docker://[^@\s]+@sha256:[0-9a-fA-F]{64}")


def unpinned_actions(directory: Path) -> list[str]:
    errors = []
    for path in sorted({*directory.glob("*.yml"), *directory.glob("*.yaml")}):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = USES.match(line)
            if match is None:
                continue
            reference = match[1]
            if reference.startswith("./"):
                continue
            pattern = CONTAINER_PIN if reference.startswith("docker://") else REMOTE_PIN
            if pattern.fullmatch(reference) is None:
                errors.append(f"{path.name}:{number}: action reference must be immutable: {reference}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-dir", type=Path, default=Path(__file__).resolve().parents[2] / ".github/workflows")
    args = parser.parse_args()
    errors = unpinned_actions(args.workflow_dir)
    if errors:
        print("\n".join(errors))
        return 1
    print("All remote workflow actions use immutable references.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
