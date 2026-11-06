"""Pushover delivery: plain text, the subject link or a fallback, and an optional photo."""

from dataclasses import dataclass, field

import httpx

from app.services.notifications.message import DeliveryResult, NotificationMessage

API_URL = "https://api.pushover.net/1/messages.json"


@dataclass(frozen=True)
class PushoverCredentials:
    api_token: str = field(repr=False)
    user_key: str = field(repr=False)


@dataclass(frozen=True)
class PushoverOptions:
    priority: int = 0
    device: str | None = None


class PushoverTransport:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def send(
        self, message: NotificationMessage, credentials: PushoverCredentials, options: PushoverOptions
    ) -> DeliveryResult:
        fields: dict[str, str | int] = {
            "token": credentials.api_token,
            "user": credentials.user_key,
            "title": message.title,
            "message": message.body,
            "html": 0,
            "priority": options.priority,
        }
        occurred = message.occurred_utc()
        if occurred is not None:
            fields["timestamp"] = int(occurred.timestamp())
        link = message.link or message.fallback_link
        if link is not None:
            fields.update(url=link.url, url_title=link.label)
        if options.device:
            fields["device"] = options.device
        photo = message.attachment
        try:
            if photo is not None:
                response = await self._client.post(
                    API_URL, data=fields, files={"attachment": (photo.filename, photo.content, photo.content_type)}
                )
            else:
                response = await self._client.post(API_URL, data=fields)
            response.raise_for_status()
            return DeliveryResult(sent=response.json().get("status") == 1, status_code=response.status_code)
        except httpx.HTTPStatusError as error:
            return DeliveryResult(sent=False, error_type=type(error).__name__, status_code=error.response.status_code)
        except Exception as error:
            # The application token travels in the form body that provider errors can echo.
            return DeliveryResult(sent=False, error_type=type(error).__name__)
