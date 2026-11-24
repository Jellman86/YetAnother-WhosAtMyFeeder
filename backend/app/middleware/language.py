from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.language import parse_accept_language


class LanguageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        accept_lang = request.headers.get("accept-language", "en")
        request.state.language = parse_accept_language(accept_lang)
        response = await call_next(request)
        return response
