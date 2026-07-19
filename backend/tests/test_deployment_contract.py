from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_recommended_monolith_defaults_to_stable_release_channel() -> None:
    compose = (REPO_ROOT / "docker-compose.monolith.yml").read_text(encoding="utf-8")
    example_env = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "${YAWAMF_MONALITHIC_TAG:-latest}" in compose
    assert "${YAWAMF_MONALITHIC_TAG:-dev}" not in compose
    assert "YAWAMF_MONALITHIC_TAG=latest" in example_env
