import re
from collections.abc import Mapping
from urllib.parse import urlencode


_HLS_ASSET_PATTERN = re.compile(
    r"^(?:master\.m3u8|index-v\d+(?:-a\d+)?\.m3u8|init-v\d+(?:-a\d+)?\.mp4|seg-\d+-v\d+(?:-a\d+)?\.m4s)$"
)
_HLS_URI_ATTRIBUTE_PATTERN = re.compile(r'URI="([^"]+)"')


def is_hls_asset(asset: str) -> bool:
    """Accept only the relative VOD assets emitted by supported Frigate versions."""
    return bool(_HLS_ASSET_PATTERN.fullmatch(asset))


def _uri_with_auth(uri: str, auth_query: str) -> str:
    if not is_hls_asset(uri):
        raise ValueError("Frigate returned an unsupported HLS asset URI")
    return f"{uri}?{auth_query}" if auth_query else uri


def rewrite_hls_playlist(body: str, query_params: Mapping[str, str]) -> str:
    """Rewrite safe relative asset URIs with only credentials needed by the browser."""
    auth_query = urlencode([(name, query_params[name]) for name in ("share", "api_key") if query_params.get(name)])
    rewritten: list[str] = []
    for line in body.splitlines():
        if line.startswith("#"):
            line = _HLS_URI_ATTRIBUTE_PATTERN.sub(
                lambda match: f'URI="{_uri_with_auth(match.group(1), auth_query)}"',
                line,
            )
        elif line.strip():
            line = _uri_with_auth(line.strip(), auth_query)
        rewritten.append(line)
    return "\n".join(rewritten) + ("\n" if body.endswith("\n") else "")
