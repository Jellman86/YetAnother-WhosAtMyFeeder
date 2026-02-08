from __future__ import annotations


def get_email_font_family(font_theme: str | None, dyslexia_font: bool) -> str:
    """
    Map the UI font theme to an email-safe font-family stack.

    Email clients often ignore remote font loading, so we include the intended
    font first and then provide robust system fallbacks.
    """
    if dyslexia_font:
        # Best-effort: many clients won't load webfonts; this still helps if installed.
        return "'OpenDyslexic', 'Arial', sans-serif"

    theme = (font_theme or "classic").strip().lower()

    if theme == "classic":
        return "'Source Serif 4', Georgia, 'Times New Roman', Times, serif"
    if theme == "clean":
        return "'Manrope', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    if theme == "studio":
        return "'Sora', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    if theme == "compact":
        return "'Instrument Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

    # "default" and unknown values
    return "'Instrument Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

