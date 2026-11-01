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

from app.services.notifications.message import Attachment, DeliveryResult, NotificationMessage, SubjectLink
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


CONFORMANCE = {"telegram": telegram_send}


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
