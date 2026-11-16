"""A channel can deliver only with its credentials: the rule About's privacy list is held to."""

import json
from pathlib import Path

import pytest

from app.config import settings
from app.services.garden_notification_transport import channel_configured

CASES = json.loads((Path(__file__).parents[1] / "fixtures" / "notification_channel_cases.json").read_text("utf-8"))[
    "cases"
]
FIELDS = {
    "discord": ("webhook_url",),
    "telegram": ("bot_token", "chat_id"),
    "pushover": ("user_key", "api_token"),
    "email": ("use_oauth", "oauth_provider", "to_email", "smtp_host", "from_email"),
}


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_a_channel_is_configured_only_with_everything_its_sender_needs(case, monkeypatch):
    for channel, fields in FIELDS.items():
        saved = case["notifications"].get(channel, {})
        for field in fields:
            empty = False if field == "use_oauth" else None
            monkeypatch.setattr(getattr(settings.notifications, channel), field, saved.get(field, empty))

    assert {channel: channel_configured(channel) for channel in FIELDS} == case["can_deliver"]
