"""The workflow policy rejects moving action references and accepts immutable ones."""

from pathlib import Path
import tempfile
import unittest

from scripts.check_action_pins import unpinned_actions


class ActionPinTests(unittest.TestCase):
    def check_reference(self, reference: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture.yml").write_text(f"jobs:\n  test:\n    steps:\n      - uses: {reference}\n")
            return unpinned_actions(root)

    def test_moving_tags_branches_and_short_hashes_are_rejected(self) -> None:
        for reference in ["actions/checkout@v7", "owner/action@main", "owner/action@abc1234"]:
            with self.subTest(reference=reference):
                errors = self.check_reference(reference)
                self.assertEqual(len(errors), 1)
                self.assertIn("fixture.yml:4", errors[0])

    def test_full_commit_references_and_subdirectory_actions_are_accepted(self) -> None:
        for reference in ["owner/action@" + "a" * 40, "owner/action/init@" + "b" * 40 + " # v4"]:
            with self.subTest(reference=reference):
                self.assertEqual(self.check_reference(reference), [])

    def test_local_actions_do_not_need_remote_pins(self) -> None:
        self.assertEqual(self.check_reference("./.github/actions/build"), [])

    def test_container_actions_require_a_digest(self) -> None:
        self.assertEqual(len(self.check_reference("docker://example/image:latest")), 1)
        self.assertEqual(self.check_reference("docker://example/image@sha256:" + "a" * 64), [])

    def test_quoted_remote_references_are_checked(self) -> None:
        self.assertEqual(len(self.check_reference("'owner/action@main'")), 1)
        self.assertEqual(self.check_reference('"owner/action@' + "a" * 40 + '"'), [])
