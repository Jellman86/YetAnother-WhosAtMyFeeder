from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_NGINX_CONFIGS = (
    REPOSITORY_ROOT / "docker/monolith/nginx.conf",
    REPOSITORY_ROOT / "apps/ui/nginx.conf",
)


@pytest.mark.parametrize("config_path", FRONTEND_NGINX_CONFIGS)
def test_frontend_assets_are_compressed_and_immutable(config_path: Path) -> None:
    config = config_path.read_text(encoding="utf-8")

    assert 'default "";' in config
    assert '"public, max-age=31536000, immutable"' in config
    assert "add_header Cache-Control $frontend_asset_cache_control always;" in config
    assert "location ^~ /assets/" in config
    assert "gzip on;" in config
    assert "gzip_vary on;" in config
    assert "gzip_min_length 1024;" in config
    assert "gzip_types text/css application/javascript image/svg+xml;" in config


@pytest.mark.parametrize("config_path", FRONTEND_NGINX_CONFIGS)
def test_frontend_document_is_revalidated_without_weakening_api_cache_headers(
    config_path: Path,
) -> None:
    config = config_path.read_text(encoding="utf-8")

    document_location = config.index("location = /index.html {")
    root_location = config.index("location / {")
    api_location = config.index("location /api/")
    document_block = config[document_location:root_location]
    root_and_static_blocks = config[root_location:api_location]

    assert "expires -1;" in document_block
    assert "add_header Cache-Control" not in root_and_static_blocks
    assert "location /api/" in config


def test_monolith_serves_live_startup_status_without_caching() -> None:
    config = (REPOSITORY_ROOT / "docker/monolith/nginx.conf").read_text(encoding="utf-8")
    entrypoint = (REPOSITORY_ROOT / "docker/monolith/entrypoint.sh").read_text(encoding="utf-8")

    assert "location = /startup-status.json" in config
    assert "alias /tmp/yawamf-startup-status.json;" in config
    assert 'add_header Cache-Control "no-store, max-age=0" always;' in config
    assert "YA_WAMF_STARTUP_STATUS_PATH" in entrypoint
    assert 'write_startup_status "starting" "launching" 5' in entrypoint
