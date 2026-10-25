from app.services.inference_execution import latest_model_execution


def test_execution_is_bound_to_the_model_and_preserves_fallback_evidence():
    old = dict(model_id="finder", provider="intel_npu", devices=["NPU"], checked_at="2026-10-24T10:00:00Z")
    fallback = old | dict(
        provider="cpu",
        requested_provider="intel_npu",
        fallback_reason="runtime_failed",
        checked_at="2026-10-24T11:00:00Z",
    )
    other = old | dict(model_id="other", checked_at="2026-10-24T12:00:00Z")
    result = latest_model_execution("finder", [None, {"bad": True}, old, fallback, other])
    assert result.provider == "cpu"
    assert result.requested_provider == "intel_npu"
    assert result.fallback_reason == "runtime_failed"
    assert latest_model_execution("unknown", [old, fallback]) is None
