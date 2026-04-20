"""Regression tests for unsupported-provider warning dedup (issue #33).

`get_active_model_spec` runs on every inference path; without deduping,
`_sanitize_installed_inference_providers` emits a fresh log warning every
time the installed model_config.json advertises a provider that is not
in the registry anymore. This spams both logs and the diagnostic bundle.
"""

from __future__ import annotations

from app.services.model_manager import ModelManager


def test_unsupported_provider_warning_only_logged_once_per_combination(monkeypatch):
    manager = ModelManager()

    calls: list[dict] = []

    def fake_warning(message, **kwargs):
        calls.append({"message": message, **kwargs})

    # structlog's BoundLogger `.warning` — patch on the module-level logger
    monkeypatch.setattr(
        "app.services.model_manager.log.warning",
        fake_warning,
    )

    for _ in range(10):
        supported, warnings = manager._sanitize_installed_inference_providers(
            installed_providers=["cpu", "intel_gpu", "obsolete_provider"],
            registry_providers=["cpu", "intel_gpu"],
            model_dir="/models/test_model",
        )
        assert supported == ["cpu", "intel_gpu"]
        # Warning string is still returned so UI/API surface stays consistent.
        assert warnings and "obsolete_provider" in warnings[0]

    # Log must only fire once for the same (model_dir, unsupported) combination.
    assert len(calls) == 1


def test_unsupported_provider_warning_logs_once_per_distinct_combination(monkeypatch):
    manager = ModelManager()

    calls: list[dict] = []
    monkeypatch.setattr(
        "app.services.model_manager.log.warning",
        lambda message, **kwargs: calls.append({"message": message, **kwargs}),
    )

    manager._sanitize_installed_inference_providers(
        installed_providers=["cpu", "foo"],
        registry_providers=["cpu"],
        model_dir="/models/a",
    )
    manager._sanitize_installed_inference_providers(
        installed_providers=["cpu", "foo"],
        registry_providers=["cpu"],
        model_dir="/models/a",
    )
    # Different model_dir — fresh warning is expected.
    manager._sanitize_installed_inference_providers(
        installed_providers=["cpu", "foo"],
        registry_providers=["cpu"],
        model_dir="/models/b",
    )
    # Different unsupported set — fresh warning is expected.
    manager._sanitize_installed_inference_providers(
        installed_providers=["cpu", "bar"],
        registry_providers=["cpu"],
        model_dir="/models/a",
    )

    assert len(calls) == 3
