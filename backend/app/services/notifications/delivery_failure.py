"""Why a channel's test message was not delivered, in words a person can act on.

A transport keeps only an error's type and the provider's status, because the rest can quote a
webhook address or a token. That is enough to name the cause and the next step, and nothing
here ever sees a credential.
"""

from typing import Literal

from app.services.notifications.message import UNREADABLE_REPLY, DeliveryResult

DeliveryChannel = Literal["discord", "pushover", "telegram"]
DeliveryFailureCause = Literal[
    "not_configured", "no_answer", "timeout", "refused", "unexpected_reply", "rate_limited", "provider_error"
]

# What a send answers when the channel has no credentials to send with.
NOT_CONFIGURED = "NotConfigured"

_CHANNEL_NAMES: dict[DeliveryChannel, str] = {"discord": "Discord", "pushover": "Pushover", "telegram": "Telegram"}
_CREDENTIAL_CHECKS: dict[DeliveryChannel, str] = {
    "discord": "Check the webhook address",
    "pushover": "Check the user key and API token",
    "telegram": "Check the bot token and chat ID",
}
_MISSING_CREDENTIALS: dict[DeliveryChannel, str] = {
    "discord": "Enter the webhook address",
    "pushover": "Enter the user key and API token",
    "telegram": "Enter the bot token and chat ID",
}


def classify_delivery_failure(result: DeliveryResult) -> DeliveryFailureCause:
    """The cause of a delivery that was not accepted, from its error type and status."""
    if result.error_type == NOT_CONFIGURED:
        return "not_configured"
    if result.error_type == UNREADABLE_REPLY:
        return "unexpected_reply"
    status = result.status_code
    if status is not None:
        if status == 429:
            return "rate_limited"
        if status >= 500:
            return "provider_error"
        # A 4xx, or a 2xx whose body said no: the provider answered and did not take the message.
        return "refused"
    if "timeout" in (result.error_type or "").lower():
        return "timeout"
    return "no_answer"


def describe_delivery_failure(cause: DeliveryFailureCause, channel: DeliveryChannel) -> str:
    """One sentence for the cause and one for what to do next."""
    name = _CHANNEL_NAMES[channel]
    if cause == "not_configured":
        return f"{name} is not set up yet. {_MISSING_CREDENTIALS[channel]}, then test again."
    if cause == "timeout":
        return f"{name} took too long to answer. Wait a moment, then test again."
    if cause == "refused":
        return f"{name} refused the message. {_CREDENTIAL_CHECKS[channel]}, then test again."
    if cause == "unexpected_reply":
        return (
            f"Something answered in place of {name}. "
            "Check for a proxy or sign-in page between YA-WAMF and the internet, then test again."
        )
    if cause == "rate_limited":
        return f"{name} is limiting messages for now. Wait a minute, then test again."
    if cause == "provider_error":
        return f"{name} reported a problem on its side. Wait a few minutes, then test again."
    # Only Discord's address is the owner's to get wrong; the others have one fixed address.
    if channel == "discord":
        return f"{name} did not answer. {_CREDENTIAL_CHECKS[channel]}, then test again."
    return f"{name} did not answer. Check that YA-WAMF can reach the internet, then test again."


def delivery_failure_payload(channel: DeliveryChannel, result: DeliveryResult) -> dict[str, str]:
    """What a failed channel test answers: a stable cause code, the channel, and the English sentence.

    The page translates the cause and its next step from the code. ``message`` is the same thing in
    English, for clients that read nothing else.
    """
    cause = classify_delivery_failure(result)
    return {
        "status": "error",
        "cause": cause,
        "channel": channel,
        "message": describe_delivery_failure(cause, channel),
    }
