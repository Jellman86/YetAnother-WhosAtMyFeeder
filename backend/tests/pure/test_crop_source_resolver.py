from io import BytesIO

from PIL import Image

from app.services.crop_source_resolver import CropSourceResolver


def _png_bytes(color: str, size: tuple[int, int] = (16, 16)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_crop_source_resolver_uses_high_quality_snapshot_when_available():
    resolver = CropSourceResolver(snapshot_loader=lambda event_id: _png_bytes("blue") if event_id == "evt-1" else None)
    original = Image.new("RGB", (8, 8), color="red")

    resolved, diagnostics = resolver.resolve(
        original,
        input_context={"is_cropped": False, "event_id": "evt-1"},
        source_preference="high_quality",
    )

    assert resolved is not original
    assert resolved.size == (16, 16)
    assert diagnostics["source_reason"] == "high_quality_snapshot"


def test_crop_source_resolver_falls_back_to_current_image_when_snapshot_missing():
    resolver = CropSourceResolver(snapshot_loader=lambda _event_id: None)
    original = Image.new("RGB", (8, 8), color="red")

    resolved, diagnostics = resolver.resolve(
        original,
        input_context={"is_cropped": False, "event_id": "evt-1"},
        source_preference="high_quality",
    )

    assert resolved is original
    assert diagnostics["source_reason"] == "high_quality_unavailable"


def test_crop_source_resolver_skips_lookup_for_already_cropped_input():
    calls: list[str] = []

    def _loader(event_id: str):
        calls.append(event_id)
        return _png_bytes("blue")

    resolver = CropSourceResolver(snapshot_loader=_loader)
    original = Image.new("RGB", (8, 8), color="red")

    resolved, diagnostics = resolver.resolve(
        original,
        input_context={"is_cropped": True, "event_id": "evt-1"},
        source_preference="high_quality",
    )

    assert resolved is original
    assert diagnostics["source_reason"] == "input_already_cropped"
    assert calls == []
