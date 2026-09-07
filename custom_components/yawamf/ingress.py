"""Home Assistant sidebar proxy for YA-WAMF."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientTimeout, web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import DOMAIN, INGRESS_URL, PANEL_URL_PATH
from .coordinator import YAWAMFDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

_INGRESS_BLOCKED_RESPONSE_HEADERS = {
    "x-frame-options",
}

_INGRESS_TOKEN_PARAM = "auth"
_INGRESS_TOKEN_COOKIE = "yawamf_ingress_token"
_RUNTIME_KEY = "_ingress_runtime"


@dataclass
class IngressRuntime:
    """What the proxy needs at request time, held in ``hass.data`` for the life of the run.

    Home Assistant views cannot be unregistered, so the view is registered once
    and looks here on every request. A reload replaces the coordinator (new URL,
    new credentials) without touching the view; an unload with no entries left
    sets the coordinator to ``None`` and the view answers 404 until the next
    setup. The token lives for the whole run so a browser that already holds
    the cookie survives a reload.
    """

    token: str
    coordinator: YAWAMFDataUpdateCoordinator | None = None
    views_registered: bool = False
    panel_registered: bool = False


def _runtime(hass: HomeAssistant) -> IngressRuntime:
    domain_data = hass.data.setdefault(DOMAIN, {})
    runtime = domain_data.get(_RUNTIME_KEY)
    if runtime is None:
        runtime = IngressRuntime(token=secrets.token_urlsafe(32))
        domain_data[_RUNTIME_KEY] = runtime
    return runtime


class YAWAMFIngressView(HomeAssistantView):
    """Proxy authenticated Home Assistant requests to the configured YA-WAMF UI."""

    url = f"{INGRESS_URL}" + "/{path:.*}"
    name = "api:yawamf:ingress"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    @property
    def runtime(self) -> IngressRuntime:
        return _runtime(self.hass)

    async def get(self, request: web.Request, path: str = "") -> web.StreamResponse:
        return await self._proxy(request, path)

    async def post(self, request: web.Request, path: str = "") -> web.StreamResponse:
        return await self._proxy(request, path)

    async def put(self, request: web.Request, path: str = "") -> web.StreamResponse:
        return await self._proxy(request, path)

    async def patch(self, request: web.Request, path: str = "") -> web.StreamResponse:
        return await self._proxy(request, path)

    async def delete(self, request: web.Request, path: str = "") -> web.StreamResponse:
        return await self._proxy(request, path)

    async def head(self, request: web.Request, path: str = "") -> web.StreamResponse:
        return await self._proxy(request, path)

    async def _proxy(self, request: web.Request, path: str) -> web.StreamResponse:
        runtime = self.runtime
        coordinator = runtime.coordinator
        if coordinator is None:
            raise web.HTTPNotFound(text="YA-WAMF sidebar is not enabled.")
        if not _is_authorized_ingress_request(request, runtime.token):
            raise web.HTTPUnauthorized()

        try:
            await coordinator.async_ensure_logged_in()
        except ConfigEntryAuthFailed as err:
            raise web.HTTPBadGateway(
                text="YA-WAMF rejected the stored credentials; reconfigure the integration."
            ) from err
        except Exception as err:  # noqa: BLE001 - an unreachable YA-WAMF is a gateway failure, not a crash
            _LOGGER.debug("YA-WAMF ingress login refresh failed", exc_info=True)
            raise web.HTTPBadGateway(text="YA-WAMF ingress could not sign in; see Home Assistant logs.") from err

        target_url = _build_target_url(coordinator.url, path, _upstream_query_string(request))
        headers = _build_forward_headers(request.headers, coordinator.headers)
        body = None if request.method in {"GET", "HEAD"} else await request.read()
        should_set_cookie = request.query.get(_INGRESS_TOKEN_PARAM) == runtime.token

        try:
            async with coordinator.session.request(
                request.method,
                target_url,
                headers=headers,
                data=body,
                allow_redirects=False,
                timeout=ClientTimeout(total=None),
            ) as upstream:
                response = web.StreamResponse(
                    status=upstream.status,
                    reason=upstream.reason,
                    headers=_response_headers(upstream.headers),
                )
                _set_ingress_cookie(response, runtime.token, should_set_cookie)

                if request.method != "HEAD" and _should_rewrite_response(upstream.headers):
                    body = await upstream.text()
                    rewritten = _rewrite_root_paths(body)
                    response_headers = _response_headers(upstream.headers)
                    response_headers.pop("Content-Type", None)
                    text_response = web.Response(
                        status=upstream.status,
                        reason=upstream.reason,
                        headers=response_headers,
                        text=rewritten,
                        content_type=upstream.content_type,
                        charset=upstream.charset,
                    )
                    _set_ingress_cookie(text_response, runtime.token, should_set_cookie)
                    return text_response

                # Preserve exact byte-length framing for unencoded bodies (e.g. media
                # clips and snapshots). Without a Content-Length the response is sent
                # chunked, which breaks <video> Range/seeking and makes clips fail to
                # load through the proxy.
                _preserve_content_length(response, upstream.headers)

                await response.prepare(request)

                if request.method != "HEAD":
                    try:
                        async for chunk in upstream.content.iter_chunked(64 * 1024):
                            await response.write(chunk)
                    except ConnectionResetError:
                        # The browser closed the connection mid-stream — normal when
                        # scrubbing/seeking a video or switching clips. The response is
                        # already partially delivered; nothing more to send.
                        _LOGGER.debug("YA-WAMF ingress client disconnected mid-stream", exc_info=True)
                        return response

                await response.write_eof()
                return response
        except ConnectionResetError:
            # Client disconnected before/at the start of streaming; not a proxy failure.
            _LOGGER.debug("YA-WAMF ingress client disconnected", exc_info=True)
            raise
        except Exception as err:  # noqa: BLE001 - HA should return a proxy failure, not crash the view
            _LOGGER.exception("YA-WAMF ingress proxy request failed")
            raise web.HTTPBadGateway(text="YA-WAMF ingress proxy failed; see Home Assistant logs.") from err


def _build_target_url(base_url: str, path: str, query_string: str) -> str:
    clean_base = base_url.rstrip("/")
    clean_path = path.lstrip("/")
    target = f"{clean_base}/{clean_path}" if clean_path else f"{clean_base}/"
    if query_string:
        target = f"{target}?{query_string}"
    return target


def _upstream_query_string(request: web.Request) -> str:
    pairs = [(key, value) for key, value in request.query.items() if key != _INGRESS_TOKEN_PARAM]
    return urlencode(pairs)


def _is_authorized_ingress_request(request: web.Request, ingress_token: str) -> bool:
    query_token = request.query.get(_INGRESS_TOKEN_PARAM)
    cookie_token = request.cookies.get(_INGRESS_TOKEN_COOKIE)
    return secrets.compare_digest(query_token or "", ingress_token) or secrets.compare_digest(
        cookie_token or "",
        ingress_token,
    )


def _set_ingress_cookie(response: web.StreamResponse, ingress_token: str, should_set_cookie: bool) -> None:
    if not should_set_cookie:
        return
    response.set_cookie(
        _INGRESS_TOKEN_COOKIE,
        ingress_token,
        httponly=True,
        samesite="Lax",
        path=INGRESS_URL,
    )


def _build_forward_headers(request_headers: Any, auth_headers: dict[str, str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request_headers.items():
        lower = key.lower()
        if lower in _HOP_BY_HOP_HEADERS or lower in {"host", "content-length"}:
            continue
        headers[key] = value

    headers.update(auth_headers)
    headers["X-Forwarded-Host"] = request_headers.get("Host", "")
    headers["X-Forwarded-Proto"] = "https"
    return headers


def _response_headers(upstream_headers: Any) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in upstream_headers.items():
        lower = key.lower()
        if (
            lower in _HOP_BY_HOP_HEADERS
            or lower in _INGRESS_BLOCKED_RESPONSE_HEADERS
            or lower in {"content-length", "content-encoding"}
        ):
            continue
        headers[key] = value
    return headers


def _preserve_content_length(response: web.StreamResponse, upstream_headers: Any) -> None:
    """Carry the upstream Content-Length onto a streamed response.

    ``_response_headers`` drops ``Content-Length`` (it is wrong once a body is
    rewritten or decompressed). For pass-through bodies that are *not* content
    encoded — media clips, snapshots — the length is exact and must be preserved
    so the browser receives real byte-length framing instead of chunked transfer.
    Chunked media breaks ``<video>`` Range/seeking and clip loading through the
    ingress proxy.
    """
    if "Content-Encoding" in upstream_headers:
        return
    raw_length = upstream_headers.get("Content-Length")
    if raw_length is None:
        return
    try:
        response.content_length = int(raw_length)
    except (TypeError, ValueError):
        return


def _should_rewrite_response(upstream_headers: Any) -> bool:
    content_type = str(upstream_headers.get("Content-Type", "")).lower()
    return any(
        media_type in content_type
        for media_type in (
            "text/html",
            "text/css",
            "javascript",
            "application/json",
            "application/manifest+json",
        )
    )


def _rewrite_root_paths(body: str) -> str:
    ingress_marker = f'<script>window.__YAWAMF_APP_BASE_PATH="{INGRESS_URL}";</script>'
    replacements = {
        'href="/': f'href="{INGRESS_URL}/',
        'src="/': f'src="{INGRESS_URL}/',
        'content="/': f'content="{INGRESS_URL}/',
        "url(/": f"url({INGRESS_URL}/",
        '"start_url": "/"': f'"start_url": "{INGRESS_URL}/"',
        '"scope": "/"': f'"scope": "{INGRESS_URL}/"',
    }
    rewritten = body
    for old, new in replacements.items():
        rewritten = rewritten.replace(old, new)

    for prefix in (
        "api/",
        "assets/",
        "src/",
        "favicon.ico",
        "favicon.png",
        "apple-touch-icon.png",
        "manifest.json",
        "pwa-192x192.png",
        "pwa-512x512.png",
        "frigate-logo.png",
        "sw.js",
    ):
        rewritten = rewritten.replace(f'"/{prefix}', f'"{INGRESS_URL}/{prefix}')
        rewritten = rewritten.replace(f"'/{prefix}", f"'{INGRESS_URL}/{prefix}")

    duplicate_prefix = f"{INGRESS_URL}{INGRESS_URL}/"
    while duplicate_prefix in rewritten:
        rewritten = rewritten.replace(duplicate_prefix, f"{INGRESS_URL}/")

    if "</head>" in rewritten and "__YAWAMF_APP_BASE_PATH" not in rewritten:
        rewritten = rewritten.replace("</head>", f"{ingress_marker}</head>", 1)

    return rewritten


async def async_register_ingress(hass: HomeAssistant, coordinator: YAWAMFDataUpdateCoordinator) -> None:
    """Point the sidebar proxy at ``coordinator`` and show the panel.

    Safe to call on every setup, including the reload that follows an options
    change: the view is registered once per run, the panel is re-registered
    with ``update=True`` so a second registration replaces rather than raises,
    and the proxy reads the coordinator from ``hass.data`` on each request.
    """
    runtime = _runtime(hass)
    runtime.coordinator = coordinator

    if not runtime.views_registered:
        hass.http.register_view(YAWAMFIngressView(hass))
        runtime.views_registered = True

    try:
        from homeassistant.components import frontend

        frontend.async_register_built_in_panel(
            hass,
            component_name="iframe",
            sidebar_title="YA-WAMF",
            sidebar_icon="mdi:bird",
            frontend_url_path=PANEL_URL_PATH,
            config={"url": f"{INGRESS_URL}/?{_INGRESS_TOKEN_PARAM}={runtime.token}"},
            require_admin=False,
            update=True,
        )
        runtime.panel_registered = True
    except Exception:  # noqa: BLE001 - proxy remains usable even if panel registration API differs
        _LOGGER.exception("Failed to register YA-WAMF Home Assistant sidebar panel")


def async_unregister_ingress(hass: HomeAssistant) -> None:
    """Hide the panel and make the proxy answer 404 until the next setup.

    ``frontend.async_remove_panel`` is a plain callback, not a coroutine; it
    must be called, not awaited.
    """
    runtime = _runtime(hass)
    runtime.coordinator = None
    if not runtime.panel_registered:
        return

    try:
        from homeassistant.components import frontend

        frontend.async_remove_panel(hass, PANEL_URL_PATH)
        runtime.panel_registered = False
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Failed to remove the YA-WAMF sidebar panel", exc_info=True)
