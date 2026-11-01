"""Discord webhook delivery: Markdown-escaped data, no mentions, and a photo attached or by address."""

import json
import re
from dataclasses import dataclass, field

import httpx

from app.services.notifications.message import DeliveryResult, NotificationMessage
from app.services.notifications.transports import http_logging  # noqa: F401  (installs the log filter)

_MARKDOWN = re.compile(r"([\\`*_~|>\[\]()])")


def escape_markdown(text: str) -> str:
    """Names and cameras are data, never Markdown controls."""
    return _MARKDOWN.sub(r"\\\1", text)


@dataclass(frozen=True)
class DiscordCredentials:
    webhook_url: str = field(repr=False)


@dataclass(frozen=True)
class DiscordOptions:
    username: str
    footer: str
    color: int | None = None
    # Bird alerts set every body line in bold.
    bold_body: bool = False


def _description(message: NotificationMessage, options: DiscordOptions) -> str:
    lines = [escape_markdown(line) for line in message.body.split("\n")]
    if options.bold_body:
        lines = [f"**{line}**" for line in lines]
    return "\n".join(lines)


class DiscordTransport:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def send(
        self, message: NotificationMessage, credentials: DiscordCredentials, options: DiscordOptions
    ) -> DeliveryResult:
        embed: dict[str, object] = {
            "title": escape_markdown(message.title),
            "description": _description(message, options),
        }
        if options.color is not None:
            embed["color"] = options.color
        occurred = message.occurred_utc()
        if occurred is not None:
            embed["timestamp"] = occurred.isoformat()
        embed["footer"] = {"text": options.footer}
        if message.link is not None:
            embed["url"] = message.link.url
        photo = message.attachment
        if photo is not None:
            embed["image"] = {"url": f"attachment://{photo.filename}"}
        elif message.image_url:
            embed["image"] = {"url": message.image_url}
        payload = {"username": options.username, "allowed_mentions": {"parse": []}, "embeds": [embed]}
        try:
            # `wait` makes Discord confirm the message exists instead of accepting it blind.
            webhook = httpx.URL(credentials.webhook_url).copy_merge_params({"wait": "true"})
            if photo is not None:
                response = await self._client.post(
                    webhook,
                    data={"payload_json": json.dumps(payload)},
                    files={"files[0]": (photo.filename, photo.content, photo.content_type)},
                )
            else:
                response = await self._client.post(webhook, json=payload)
            response.raise_for_status()
            return DeliveryResult(sent=True, status_code=response.status_code)
        except httpx.HTTPStatusError as error:
            return DeliveryResult(sent=False, error_type=type(error).__name__, status_code=error.response.status_code)
        except Exception as error:
            # The webhook URL is the credential, and request errors can quote it: keep only the type.
            return DeliveryResult(sent=False, error_type=type(error).__name__)
