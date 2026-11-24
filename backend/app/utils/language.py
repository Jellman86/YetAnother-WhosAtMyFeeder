"""Language detection utility for extracting user language from HTTP headers."""

from fastapi import Request

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "es", "fr", "de", "ja", "zh", "ru", "pt", "it")
_SUPPORTED_SET = frozenset(SUPPORTED_LANGUAGES)


def parse_accept_language(header: str | None) -> str:
    """Select the highest-priority supported two-letter language from an Accept-Language header.

    Follows RFC 9110 preference weights (`;q=...`), treats tags case-insensitively, skips
    entries with `q=0`, and preserves declaration order on ties. Falls back to `'en'`.
    """
    if not header or not isinstance(header, str):
        return "en"

    candidates: list[tuple[float, int, str]] = []
    for index, raw_part in enumerate(header.split(",")):
        part = raw_part.strip()
        if not part:
            continue
        segments = [seg.strip() for seg in part.split(";")]
        tag = segments[0].lower()
        if not tag or tag == "*":
            continue
        primary = tag.split("-", 1)[0].strip()
        if primary not in _SUPPORTED_SET:
            continue

        quality = 1.0
        valid_q = True
        for param in segments[1:]:
            if "=" not in param:
                continue
            key, raw_val = param.split("=", 1)
            if key.strip().lower() == "q":
                try:
                    quality = float(raw_val.strip())
                except ValueError:
                    valid_q = False
                    break
        if not valid_q or quality <= 0.0:
            continue
        candidates.append((min(quality, 1.0), index, primary))

    if not candidates:
        return "en"
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def get_user_language(request: Request) -> str:
    """Extract user language from Accept-Language header.

    Returns two-letter language code (e.g., 'en', 'es', 'zh').
    Falls back to 'en' if unsupported or missing.
    """
    accept_lang = request.headers.get("Accept-Language") or request.headers.get("accept-language")
    return parse_accept_language(accept_lang)
