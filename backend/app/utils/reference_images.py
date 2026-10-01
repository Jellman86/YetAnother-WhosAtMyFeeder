"""Keep reference photographs within the provider's standard thumbnail sizes."""

import re
from urllib.parse import unquote, urlsplit, urlunsplit


_REFERENCE_WIDTH = 960
_WIKIMEDIA_HOSTS = {"upload.wikimedia.org", "thumb.wikimedia.org"}
_PHOTO_PATH = re.compile(
    r"^/wikipedia/(?P<repository>commons|en)/(?P<thumbnail>thumb/)?"
    r"(?P<shard>[0-9a-f]/[0-9a-f]{2})/(?P<filename>[^/]+\.(?:jpe?g|png))"
    r"(?:/(?P<width>[0-9]{1,5})px-(?P=filename))?$",
    re.IGNORECASE,
)


def bounded_reference_thumbnail(url: str | None) -> str | None:
    """Bound known Wikimedia raster URLs, including photographs in older cache rows.

    960px is a supported Wikimedia thumbnail bucket. Unknown providers, rendered
    SVGs and other formats retain their own URL rather than guessing a rendition.
    This projects cached metadata without a refresh or a catalogue write.
    """
    if not url:
        return url
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    if parsed.scheme != "https" or parsed.netloc not in _WIKIMEDIA_HOSTS:
        return url
    match = _PHOTO_PATH.fullmatch(parsed.path)
    if not match:
        return url
    filename = match["filename"]
    if any(character in unquote(filename) for character in ("/", "\\")):
        return url
    width = match["width"]
    if match["thumbnail"]:
        if width is None or int(width) <= _REFERENCE_WIDTH:
            return url
    elif width is not None:
        return url
    path = f"/wikipedia/{match['repository']}/thumb/{match['shard']}/{filename}/{_REFERENCE_WIDTH}px-{filename}"
    return urlunsplit(parsed._replace(path=path))
