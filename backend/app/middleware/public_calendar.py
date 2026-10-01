from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.utils.public_access import public_calendar_scope


class PublicCalendarMiddleware:
    """Keep public history, projection and evidence on the same request calendar."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with public_calendar_scope() as calendar:

            async def send_response(message: Message) -> None:
                await send(message)
                if message["type"] == "http.response.body" and not message.get("more_body", False):
                    # Starlette background tasks run after the body, before the
                    # ASGI callable returns. They must use a fresh policy day.
                    calendar.close()

            await self.app(scope, receive, send_response)
