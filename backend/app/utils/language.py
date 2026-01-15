"""Language detection utility for extracting user language from HTTP headers."""

from fastapi import Request


def get_user_language(request: Request) -> str:
    """
    Extract user language from Accept-Language header.

    Returns two-letter language code (e.g., 'en', 'es', 'zh').
    Falls back to 'en' if unsupported or missing.

    Args:
        request: FastAPI Request object

    Returns:
        str: Two-letter language code

    Examples:
        >>> # Accept-Language: en-US,en;q=0.9,es;q=0.8
        >>> get_user_language(request)
        'en'

        >>> # Accept-Language: zh-CN
        >>> get_user_language(request)
        'zh'
    """
    accept_lang = request.headers.get("Accept-Language", "en")

    # Parse: "en-US,en;q=0.9,es;q=0.8" -> "en"
    # Take first locale, split on comma, hyphen, and semicolon
    primary_lang = accept_lang.split(",")[0].split("-")[0].split(";")[0].strip()

    # Validate against supported languages
    supported = ["en", "es", "fr", "de", "ja", "zh"]
    return primary_lang if primary_lang in supported else "en"
