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

    # `configured` is given only where the settings check passes and the token lookup then stops the send.
    assert {channel: channel_configured(channel) for channel in FIELDS} == case.get("configured", case["can_deliver"])


def test_a_disconnected_email_account_is_stopped_by_the_token_lookup_before_any_request():
    """Why About must not read the provider name as a connection: no token, no send."""
    import inspect

    from app.services.smtp_service import SMTPService

    source = inspect.getsource(SMTPService._get_oauth_token)
    assert "FROM oauth_tokens WHERE provider = ?" in source
    assert "if not row:\n                    return None" in source
