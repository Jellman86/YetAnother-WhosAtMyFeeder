import pytest

from app.utils.hls import is_hls_asset, rewrite_hls_playlist


@pytest.mark.parametrize(
    "asset",
    [
        "master.m3u8",
        "index-v1.m3u8",
        "index-v1-a1.m3u8",
        "init-v2.mp4",
        "init-v2-a3.mp4",
        "seg-42-v2.m4s",
        "seg-42-v2-a3.m4s",
    ],
)
def test_expected_frigate_hls_assets_are_allowed(asset: str):
    assert is_hls_asset(asset)


@pytest.mark.parametrize(
    "asset",
    [
        "../master.m3u8",
        "https://example.invalid/seg-1-v1.m4s",
        "seg-1-v1.m4s?token=upstream",
        "segment.ts",
        "key.bin",
    ],
)
def test_unexpected_hls_assets_are_rejected(asset: str):
    assert not is_hls_asset(asset)


def test_playlist_rewrite_preserves_line_endings_and_filters_query_params():
    playlist = '#EXTM3U\n#EXT-X-MAP:URI="init-v1.mp4"\nseg-1-v1.m4s\n'

    rewritten = rewrite_hls_playlist(
        playlist,
        {"share": "share token", "api_key": "key/value", "ignored": "no"},
    )

    assert rewritten == (
        '#EXTM3U\n#EXT-X-MAP:URI="init-v1.mp4?share=share+token&api_key=key%2Fvalue"\n'
        "seg-1-v1.m4s?share=share+token&api_key=key%2Fvalue\n"
    )
