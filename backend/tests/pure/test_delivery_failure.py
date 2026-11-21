"""Why a channel test failed, read from the delivery result and worded with the next step."""

import pytest

from app.services.notifications.delivery_failure import (
    classify_delivery_failure,
    delivery_failure_payload,
    describe_delivery_failure,
)
from app.services.notifications.message import DeliveryResult


@pytest.mark.parametrize(
    "result, cause",
    [
        (DeliveryResult(sent=False, error_type="NotConfigured"), "not_configured"),
        (DeliveryResult(sent=False, error_type="ConnectError"), "no_answer"),
        (DeliveryResult(sent=False, error_type="RemoteProtocolError"), "no_answer"),
        (DeliveryResult(sent=False, error_type="ConnectTimeout"), "timeout"),
        (DeliveryResult(sent=False, error_type="ReadTimeout"), "timeout"),
        (DeliveryResult(sent=False, error_type="TimeoutError"), "timeout"),
        (DeliveryResult(sent=False, error_type="HTTPStatusError", status_code=400), "refused"),
        (DeliveryResult(sent=False, error_type="HTTPStatusError", status_code=401), "refused"),
        (DeliveryResult(sent=False, error_type="HTTPStatusError", status_code=404), "refused"),
        (DeliveryResult(sent=False, error_type="HTTPStatusError", status_code=429), "rate_limited"),
        (DeliveryResult(sent=False, error_type="HTTPStatusError", status_code=500), "provider_error"),
        (DeliveryResult(sent=False, error_type="HTTPStatusError", status_code=503), "provider_error"),
        # The provider answered 200 and still said no, as Telegram's "ok": false does.
        (DeliveryResult(sent=False, status_code=200), "refused"),
        # Something answered 200 with a body the channel never sends, as a proxy or captive portal does.
        (DeliveryResult(sent=False, error_type="UnreadableReply", status_code=200), "unexpected_reply"),
        (DeliveryResult(sent=False), "no_answer"),
    ],
)
def test_classify_delivery_failure_reads_the_cause_from_the_result(result, cause):
    assert classify_delivery_failure(result) == cause


def test_a_discord_webhook_that_does_not_answer_points_at_the_webhook_address():
    assert describe_delivery_failure("no_answer", "discord") == (
        "Discord did not answer. Check the webhook address, then test again."
    )


@pytest.mark.parametrize("channel, name", [("pushover", "Pushover"), ("telegram", "Telegram")])
def test_a_fixed_address_channel_that_does_not_answer_points_at_the_network(channel, name):
    assert describe_delivery_failure("no_answer", channel) == (
        f"{name} did not answer. Check that YA-WAMF can reach the internet, then test again."
    )


@pytest.mark.parametrize(
    "channel, check",
    [
        ("discord", "Check the webhook address"),
        ("pushover", "Check the user key and API token"),
        ("telegram", "Check the bot token and chat ID"),
    ],
)
def test_a_refused_message_names_the_credentials_to_check(channel, check):
    sentence = describe_delivery_failure("refused", channel)
    assert "refused the message" in sentence
    assert sentence.endswith(f"{check}, then test again.")


@pytest.mark.parametrize(
    "cause", ["not_configured", "no_answer", "timeout", "refused", "rate_limited", "provider_error"]
)
@pytest.mark.parametrize("channel", ["discord", "pushover", "telegram"])
def test_every_cause_states_a_next_step_for_every_channel(cause, channel):
    sentence = describe_delivery_failure(cause, channel)
    # A cause sentence and a next-step sentence.
    assert sentence.count(".") >= 2
    assert "Error" not in sentence and "HTTP" not in sentence


def test_the_payload_carries_the_cause_code_the_channel_and_the_english_sentence():
    payload = delivery_failure_payload("telegram", DeliveryResult(sent=False, error_type="ReadTimeout"))
    assert payload == {
        "status": "error",
        "cause": "timeout",
        "channel": "telegram",
        "message": "Telegram took too long to answer. Wait a moment, then test again.",
    }


@pytest.mark.parametrize("channel, name", [("discord", "Discord"), ("pushover", "Pushover"), ("telegram", "Telegram")])
def test_a_reply_the_channel_never_sends_points_at_something_in_between(channel, name):
    assert describe_delivery_failure("unexpected_reply", channel) == (
        f"Something answered in place of {name}. "
        "Check for a proxy or sign-in page between YA-WAMF and the internet, then test again."
    )
