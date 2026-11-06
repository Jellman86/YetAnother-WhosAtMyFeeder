"""Shared channel transports: what each sends, how it escapes, and what a failure reveals.

HTTP is mocked at the boundary with `httpx.MockTransport`; nothing is ever sent. Every
transport in `CONFORMANCE` must make one request per send, attach a photo only when given
one, and report failures by type and status alone.
"""

import json
import logging
from urllib.parse import quote, unquote

import httpx
import pytest
from structlog.testing import capture_logs

from datetime import datetime, timedelta, timezone

from app.services.notifications.message import Attachment, DeliveryResult, NotificationMessage, SubjectLink
from app.services.notifications.transports.discord import DiscordCredentials, DiscordOptions, DiscordTransport
from app.services.notifications.transports.email import EmailCredentials, EmailOptions, EmailTransport
from app.services.notifications.transports.pushover import (
    API_URL as PUSHOVER_URL,
    PushoverCredentials,
    PushoverOptions,
    PushoverTransport,
)
from app.services.notifications.transports.telegram import (
    CAPTION_TEXT_LIMIT,
    MESSAGE_TEXT_LIMIT,
    TITLE_LIMIT_WITH_BODY,
    TelegramCredentials,
    TelegramOptions,
    TelegramTransport,
)

TOKEN = "123456:DUMMY-TRANSPORT-CREDENTIAL"
PHOTO = Attachment("garden.jpg", b"\xff\xd8\xff fixture-jpeg")
LINK = SubjectLink("https://owner.test/feeder/events?garden_capture=abc&x=1", "View capture")


class Recorder:
    """An HTTP boundary that answers every request with one canned response, or raises."""

    def __init__(self, answer: object = None) -> None:
        self.requests: list[httpx.Request] = []
        self.answer = answer

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        if isinstance(self.answer, httpx.Response):
            return self.answer
        return httpx.Response(200, json={"ok": True, "status": 1})


async def telegram_send(recorder: Recorder, message: NotificationMessage, options=TelegramOptions()):
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as client:
        return await TelegramTransport(client).send(message, TelegramCredentials(TOKEN, "owner-chat"), options)


def multipart_fields(request: httpx.Request) -> dict[str, str]:
    """The text fields of a multipart body, by name."""
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields = {}
    for part in request.content.split(b"--" + boundary):
        head, _, value = part.partition(b"\r\n\r\n")
        if b'name="' in head and b"filename=" not in head:
            name = head.split(b'name="')[1].split(b'"')[0].decode()
            fields[name] = value.rstrip(b"\r\n").decode()
    return fields


WEBHOOK = f"https://discord.com/api/webhooks/1/{TOKEN}?thread_id=7"
GARDEN_DISCORD = DiscordOptions(username="YA-WAMF", footer="YA-WAMF Garden")


async def discord_send(recorder: Recorder, message: NotificationMessage, options=GARDEN_DISCORD):
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as client:
        return await DiscordTransport(client).send(message, DiscordCredentials(WEBHOOK), options)


async def pushover_send(recorder: Recorder, message: NotificationMessage, options=PushoverOptions()):
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as client:
        return await PushoverTransport(client).send(message, PushoverCredentials(TOKEN, "owner-key"), options)


CONFORMANCE = {"telegram": telegram_send, "discord": discord_send, "pushover": pushover_send}


# --- Conformance: every channel transport -------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", CONFORMANCE)
@pytest.mark.parametrize("attachment", [None, PHOTO])
async def test_a_send_is_one_request_that_attaches_a_photo_only_when_given_one(channel, attachment):
    recorder = Recorder()
    result = await CONFORMANCE[channel](recorder, NotificationMessage("Title", "Body", attachment=attachment))
    assert result.sent is True
    assert len(recorder.requests) == 1
    assert (PHOTO.content in recorder.requests[0].content) is (attachment is not None)


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", CONFORMANCE)
@pytest.mark.parametrize(
    "answer,error_type,status",
    [
        (httpx.Response(401, json={"ok": False}), "HTTPStatusError", 401),
        (httpx.Response(429, json={"ok": False}), "HTTPStatusError", 429),
        (httpx.Response(500, text=f"upstream echoed {TOKEN}"), "HTTPStatusError", 500),
        (httpx.ReadTimeout(f"Timeout accessing bot{TOKEN}"), "ReadTimeout", None),
        (RuntimeError(f"Provider failure {TOKEN}"), "RuntimeError", None),
    ],
)
async def test_a_failure_is_reported_once_by_type_and_status_without_provider_text(
    channel, answer, error_type, status, caplog
):
    recorder = Recorder(answer)
    caplog.set_level(logging.DEBUG, logger="httpx")
    with capture_logs() as logs:
        result = await CONFORMANCE[channel](recorder, NotificationMessage("Title", "Body"))
    assert result == DeliveryResult(sent=False, error_type=error_type, status_code=status)
    assert len(recorder.requests) == 1, "a failed send is never replayed"
    rendered = repr(result) + json.dumps(logs) + caplog.text
    assert TOKEN not in unquote(rendered) and quote(TOKEN, safe="") not in rendered


# --- Telegram -----------------------------------------------------------------------------------


def test_telegram_credentials_never_print_their_values():
    assert TOKEN not in repr(TelegramCredentials(TOKEN, "owner-chat"))
    assert "owner-chat" not in repr(TelegramCredentials(TOKEN, "owner-chat"))
    assert PHOTO.content not in repr(PHOTO).encode()


@pytest.mark.asyncio
async def test_telegram_text_escapes_data_and_links_the_subject_with_a_button():
    recorder = Recorder()
    message = NotificationMessage('Cat <b>& "x"', "Seen on <patio>", link=LINK)
    assert (await telegram_send(recorder, message)).sent is True
    request = recorder.requests[0]
    assert unquote(str(request.url)) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert json.loads(request.content) == {
        "chat_id": "owner-chat",
        "text": "<b>Cat &lt;b&gt;&amp; &quot;x&quot;</b>\nSeen on &lt;patio&gt;",
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
        "reply_markup": {"inline_keyboard": [[{"text": "View capture", "url": LINK.url}]]},
    }


@pytest.mark.asyncio
async def test_telegram_photo_is_a_multipart_caption_with_a_json_button():
    recorder = Recorder()
    message = NotificationMessage("Cat <b>", "Seen & named", link=LINK, attachment=PHOTO)
    assert (await telegram_send(recorder, message)).sent is True
    request = recorder.requests[0]
    assert str(request.url).endswith("/sendPhoto")
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="photo"; filename="garden.jpg"' in request.content
    assert b"Content-Type: image/jpeg" in request.content
    fields = multipart_fields(request)
    assert fields["chat_id"] == "owner-chat"
    assert fields["caption"] == "<b>Cat &lt;b&gt;</b>\nSeen &amp; named"
    assert fields["parse_mode"] == "HTML"
    assert json.loads(fields["reply_markup"]) == {"inline_keyboard": [[{"text": "View capture", "url": LINK.url}]]}


@pytest.mark.asyncio
async def test_telegram_without_a_subject_link_has_no_button_and_points_text_at_the_fallback():
    fallback = SubjectLink('http://frigate/snap.jpg?a=1&b="2"', "View Snapshot")
    recorder = Recorder()
    await telegram_send(recorder, NotificationMessage("Blue Jay", fallback_link=fallback), TelegramOptions(icon="🐦"))
    payload = json.loads(recorder.requests[0].content)
    assert "reply_markup" not in payload
    assert payload["text"] == (
        '🐦 <b>Blue Jay</b>\n<a href="http://frigate/snap.jpg?a=1&amp;b=&quot;2&quot;">View Snapshot</a>'
    )

    await telegram_send(recorder, NotificationMessage("Blue Jay", fallback_link=fallback, attachment=PHOTO))
    assert "View Snapshot" not in multipart_fields(recorder.requests[1])["caption"]

    await telegram_send(recorder, NotificationMessage("Blue Jay", link=LINK, fallback_link=fallback))
    assert "View Snapshot" not in json.loads(recorder.requests[2].content)["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attachment,limit", [(None, MESSAGE_TEXT_LIMIT), (PHOTO, CAPTION_TEXT_LIMIT)], ids=["text", "photo"]
)
async def test_telegram_clips_raw_text_before_escaping_so_entities_stay_whole(attachment, limit):
    recorder = Recorder()
    await telegram_send(recorder, NotificationMessage("&" * 5000, attachment=attachment))
    await telegram_send(recorder, NotificationMessage("&" * 5000, "<" * 5000, attachment=attachment))

    def text(request):
        return multipart_fields(request)["caption"] if attachment else json.loads(request.content)["text"]

    title_only, with_body = text(recorder.requests[0]), text(recorder.requests[1])
    assert title_only == "<b>" + "&amp;" * (limit - 1) + "…</b>"
    title, body = with_body.split("\n")
    assert title == "<b>" + "&amp;" * (TITLE_LIMIT_WITH_BODY - 1) + "…</b>"
    assert body == "&lt;" * (limit - TITLE_LIMIT_WITH_BODY - 1) + "…"


@pytest.mark.asyncio
async def test_telegram_counts_only_an_ok_answer_as_sent():
    recorder = Recorder(httpx.Response(200, json={"ok": False}))
    assert await telegram_send(recorder, NotificationMessage("Title")) == DeliveryResult(sent=False, status_code=200)


# --- Discord ------------------------------------------------------------------------------------


def test_discord_and_pushover_credentials_never_print_their_values():
    assert TOKEN not in repr(DiscordCredentials(WEBHOOK))
    assert TOKEN not in repr(PushoverCredentials(TOKEN, "owner-key")) and "owner-key" not in repr(
        PushoverCredentials(TOKEN, "owner-key")
    )


@pytest.mark.asyncio
async def test_discord_escapes_data_never_mentions_and_waits_for_the_created_message():
    recorder = Recorder()
    seen = datetime(2026, 11, 1, 9, 30, tzinfo=timezone(timedelta(hours=2)))
    message = NotificationMessage("Cat *x* @everyone", "on [patio](x)\nnamed_one", link=LINK, occurred_at=seen)
    assert (await discord_send(recorder, message)).sent is True
    request = recorder.requests[0]
    assert request.url.params["wait"] == "true" and request.url.params["thread_id"] == "7"
    assert json.loads(request.content) == {
        "username": "YA-WAMF",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": "Cat \\*x\\* @everyone",
                "description": "on \\[patio\\]\\(x\\)\nnamed\\_one",
                "timestamp": "2026-11-01T07:30:00+00:00",
                "footer": {"text": "YA-WAMF Garden"},
                "url": LINK.url,
            }
        ],
    }


@pytest.mark.asyncio
async def test_discord_bird_options_bold_each_line_add_colour_and_show_a_snapshot_by_address():
    recorder = Recorder()
    bird = DiscordOptions(username="Feeder", footer="YA-WAMF", color=3066993, bold_body=True)
    message = NotificationMessage("Robin", "Robin seen\nHeard too", image_url="http://frigate/snap.jpg")
    await discord_send(recorder, message, bird)
    embed = json.loads(recorder.requests[0].content)["embeds"][0]
    assert embed["description"] == "**Robin seen**\n**Heard too**"
    assert embed["color"] == 3066993 and embed["footer"] == {"text": "YA-WAMF"}
    assert embed["image"] == {"url": "http://frigate/snap.jpg"} and "timestamp" not in embed


@pytest.mark.asyncio
async def test_discord_photo_is_attached_and_named_by_the_embed_instead_of_any_address():
    recorder = Recorder()
    await discord_send(recorder, NotificationMessage("Cat", "Seen", attachment=PHOTO, image_url="http://frigate/x.jpg"))
    request = recorder.requests[0]
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="files[0]"; filename="garden.jpg"' in request.content
    payload = json.loads(multipart_fields(request)["payload_json"])
    assert payload["embeds"][0]["image"] == {"url": "attachment://garden.jpg"}
    assert b"frigate/x.jpg" not in request.content


# --- Pushover -----------------------------------------------------------------------------------


def pushover_fields(request: httpx.Request) -> dict[str, str]:
    from urllib.parse import parse_qs

    if request.headers["content-type"].startswith("multipart/form-data"):
        return multipart_fields(request)
    return {key: values[0] for key, values in parse_qs(request.content.decode()).items()}


@pytest.mark.asyncio
async def test_pushover_sends_plain_text_with_the_subject_link_time_priority_and_device():
    recorder = Recorder()
    message = NotificationMessage(
        "Cat <b>",
        "Seen & named",
        link=LINK,
        fallback_link=SubjectLink("http://frigate/snap.jpg", "View Snapshot"),
        occurred_at=datetime(2026, 11, 1, 9, 30),
    )
    assert (await pushover_send(recorder, message, PushoverOptions(priority=1, device="phone"))).sent is True
    request = recorder.requests[0]
    assert str(request.url) == PUSHOVER_URL
    assert pushover_fields(request) == {
        "token": TOKEN,
        "user": "owner-key",
        "title": "Cat <b>",
        "message": "Seen & named",
        "html": "0",
        "priority": "1",
        "timestamp": str(int(datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc).timestamp())),
        "url": LINK.url,
        "url_title": "View capture",
        "device": "phone",
    }


@pytest.mark.asyncio
async def test_pushover_falls_back_to_the_snapshot_link_and_attaches_a_photo():
    recorder = Recorder()
    fallback = SubjectLink("http://frigate/snap.jpg", "View Snapshot")
    await pushover_send(recorder, NotificationMessage("Robin", "Seen", fallback_link=fallback, attachment=PHOTO))
    request = recorder.requests[0]
    assert b'name="attachment"; filename="garden.jpg"' in request.content
    fields = pushover_fields(request)
    assert fields["url"] == fallback.url and fields["url_title"] == "View Snapshot"
    assert "timestamp" not in fields and "device" not in fields


@pytest.mark.asyncio
async def test_pushover_counts_only_an_accepted_answer_as_sent():
    recorder = Recorder(httpx.Response(200, json={"status": 0}))
    assert await pushover_send(recorder, NotificationMessage("Title")) == DeliveryResult(sent=False, status_code=200)


@pytest.mark.parametrize("logger", ["httpx", "httpcore.http11"])
def test_verbose_http_logs_hide_a_configured_discord_webhook_on_any_host(monkeypatch, caplog, logger):
    from app.config import settings

    webhook = "https://discord.example.test/api/webhooks/9/DUMMY-SELF-HOSTED-WEBHOOK"
    monkeypatch.setattr(settings.notifications.discord, "webhook_url", webhook)
    caplog.set_level(logging.DEBUG, logger=logger)
    logging.getLogger(logger).info("HTTP Request: POST %s", webhook + "?wait=true")
    assert "DUMMY-SELF-HOSTED-WEBHOOK" not in caplog.text
    assert "REDACTED" in caplog.text and "HTTP Request" in caplog.text


# --- Email --------------------------------------------------------------------------------------


class FakeMailer:
    """The SMTP/OAuth boundary: records each send and answers, or raises, as told."""

    def __init__(self, answer: object = True) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.answer = answer

    async def _record(self, kind: str, kwargs: dict[str, object]) -> bool:
        self.calls.append((kind, kwargs))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer is True

    async def send_email_oauth(self, **kwargs):
        return await self._record("oauth", kwargs)

    async def send_email_password(self, **kwargs):
        return await self._record("password", kwargs)


SMTP = EmailCredentials(
    to_email="owner@example.test",
    from_email="feeder@example.test",
    smtp_host="smtp.example.test",
    smtp_port=465,
    smtp_username="feeder",
    smtp_password="DUMMY-SMTP-PASSWORD",
    use_tls=False,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("attachment", [None, PHOTO])
async def test_email_sends_once_and_embeds_a_photo_only_when_given_one(attachment):
    mailer = FakeMailer()
    result = await EmailTransport(mailer).send(NotificationMessage("Title", "Body", attachment=attachment), SMTP)
    assert result == DeliveryResult(sent=True)
    assert len(mailer.calls) == 1
    kwargs = mailer.calls[0][1]
    assert kwargs["image_data"] == (PHOTO.content if attachment else None)
    assert ("cid:bird_snapshot" in str(kwargs["html_body"])) is (attachment is not None)


@pytest.mark.asyncio
async def test_email_over_smtp_escapes_data_and_links_the_subject():
    mailer = FakeMailer()
    message = NotificationMessage('Cat <b>& "x"', "Seen <here>", link=LINK, attachment=PHOTO)
    await EmailTransport(mailer).send(message, SMTP)
    assert mailer.calls == [
        (
            "password",
            {
                "smtp_host": "smtp.example.test",
                "smtp_port": 465,
                "username": "feeder",
                "password": "DUMMY-SMTP-PASSWORD",
                "from_email": "feeder@example.test",
                "to_email": "owner@example.test",
                "subject": 'Cat <b>& "x"',
                "html_body": (
                    "<h1>Cat &lt;b&gt;&amp; &quot;x&quot;</h1><p>Seen &lt;here&gt;</p>"
                    '<p><img src="cid:bird_snapshot" alt="Cat &lt;b&gt;&amp; &quot;x&quot;" style="max-width:100%"></p>'
                    '<p><a href="https://owner.test/feeder/events?garden_capture=abc&amp;x=1">View capture</a></p>'
                ),
                "plain_body": f'Cat <b>& "x"\nSeen <here>\n{LINK.url}',
                "use_tls": False,
                "image_data": PHOTO.content,
            },
        )
    ]


@pytest.mark.asyncio
async def test_email_over_oauth_uses_the_provider_and_a_builder_rendered_body():
    mailer = FakeMailer()
    oauth = EmailCredentials(to_email="owner@example.test", oauth_provider="gmail")
    rendered = EmailOptions(html_body="<p>template</p>", plain_body="template")
    await EmailTransport(mailer).send(NotificationMessage("Robin"), oauth, rendered)
    assert mailer.calls == [
        (
            "oauth",
            {
                "provider": "gmail",
                "to_email": "owner@example.test",
                "from_email": None,
                "subject": "Robin",
                "html_body": "<p>template</p>",
                "plain_body": "template",
                "image_data": None,
            },
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer,expected",
    [
        (False, DeliveryResult(sent=False)),
        (OSError("535 auth failed for DUMMY-SMTP-PASSWORD"), DeliveryResult(sent=False, error_type="OSError")),
    ],
)
async def test_email_failure_is_reported_once_without_provider_text(answer, expected):
    mailer = FakeMailer(answer)
    with capture_logs() as logs:
        result = await EmailTransport(mailer).send(NotificationMessage("Title", "Body"), SMTP)
    assert result == expected
    assert len(mailer.calls) == 1
    assert "DUMMY-SMTP-PASSWORD" not in repr(result) + json.dumps(logs) + repr(SMTP)
