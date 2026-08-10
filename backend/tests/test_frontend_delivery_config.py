from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_NGINX_CONFIGS = (
    REPOSITORY_ROOT / "docker/monolith/nginx.conf",
    REPOSITORY_ROOT / "apps/ui/nginx.conf",
)
FRONTEND_NGINX_UPSTREAMS = (
    (REPOSITORY_ROOT / "docker/monolith/nginx.conf", "http://127.0.0.1:8000"),
    (REPOSITORY_ROOT / "apps/ui/nginx.conf", "http://yawamf-backend:8000"),
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


@pytest.mark.parametrize(("config_path", "backend_upstream"), FRONTEND_NGINX_UPSTREAMS)
def test_operational_probes_are_exact_public_backend_routes(
    config_path: Path,
    backend_upstream: str,
) -> None:
    config = config_path.read_text(encoding="utf-8")

    for endpoint in ("health", "ready"):
        location = f"location = /{endpoint} {{"
        block_start = config.index(location)
        block_end = config.index("\n    }", block_start)
        block = config[block_start:block_end]

        assert f"proxy_pass {backend_upstream}/{endpoint};" in block
        assert "add_header " not in block

    assert "location /health {" not in config
    assert "location /ready {" not in config


def test_monolith_healthcheck_exercises_public_readiness_route() -> None:
    healthcheck = (REPOSITORY_ROOT / "docker/monolith/healthcheck.sh").read_text(encoding="utf-8")

    assert "http://127.0.0.1:8080/health" in healthcheck
    assert "http://127.0.0.1:8080/ready" in healthcheck
    assert "http://127.0.0.1:8000/ready" not in healthcheck


def test_monolith_serves_live_startup_status_without_caching() -> None:
    config = (REPOSITORY_ROOT / "docker/monolith/nginx.conf").read_text(encoding="utf-8")
    entrypoint = (REPOSITORY_ROOT / "docker/monolith/entrypoint.sh").read_text(encoding="utf-8")

    assert "location = /startup-status.json" in config
    assert "alias /tmp/yawamf-startup-status.json;" in config
    assert 'add_header Cache-Control "no-store, max-age=0" always;' in config
    assert "YA_WAMF_STARTUP_STATUS_PATH" in entrypoint
    assert 'write_startup_status "starting" "launching" 5' in entrypoint


def test_monolith_access_logs_omit_query_strings() -> None:
    main_config = (REPOSITORY_ROOT / "docker/monolith/nginx-main.conf").read_text(encoding="utf-8")
    entrypoint = (REPOSITORY_ROOT / "docker/monolith/entrypoint.sh").read_text(encoding="utf-8")

    assert '"$request_method $uri $server_protocol"' in main_config
    assert "access_log /dev/stdout safe_access;" in main_config
    assert "access_log /dev/stdout;" not in main_config
    assert "$args" not in main_config
    assert "$request_uri" not in main_config
    assert "$http_referer" not in main_config
    assert "--no-access-log" in entrypoint


def test_monolith_compose_rotates_container_logs() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.monolith.yml").read_text(encoding="utf-8")

    assert "logging:" in compose
    assert 'max-size: "${CONTAINER_LOG_MAX_SIZE:-10m}"' in compose
    assert 'max-file: "${CONTAINER_LOG_MAX_FILES:-3}"' in compose
    assert "DB_PRE_MIGRATION_BACKUP_RETENTION=${DB_PRE_MIGRATION_BACKUP_RETENTION:-10}" in compose
