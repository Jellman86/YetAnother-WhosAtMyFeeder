from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class LanguageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract Accept-Language header
        accept_lang = request.headers.get("accept-language", "en")
        
        # Parse and extract primary language
        # Take first locale, split on comma, hyphen, and semicolon
        # "en-US,en;q=0.9,es;q=0.8" -> "en"
        try:
            primary_lang = accept_lang.split(',')[0].split('-')[0].split(';')[0].strip().lower()
        except (AttributeError, IndexError):
            primary_lang = "en"

        # Store in request state
        # Validate against supported languages: 
        # matches locales in YA-WAMF/apps/ui/src/lib/i18n/locales
        supported_langs = ["en", "es", "fr", "de", "ja", "zh", "ru", "pt", "it"]
        request.state.language = primary_lang if primary_lang in supported_langs else "en"

        response = await call_next(request)
        return response
