"""Home Assistant sidebar proxy for YA-WAMF."""
from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientTimeout, web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import INGRESS_URL, PANEL_URL_PATH
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
_PUBLIC_ASSET_PATHS = (
    "favicon.ico",
    "favicon.png",
    "apple-touch-icon.png",
    "manifest.json",
    "pwa-192x192.png",
    "pwa-512x512.png",
    "frigate-logo.png",
)


class YAWAMFIngressView(HomeAssistantView):
    """Proxy authenticated Home Assistant requests to the configured YA-WAMF UI."""

    url = f"{INGRESS_URL}" + "/{path:.*}"
    name = "api:yawamf:ingress"
    requires_auth = False

    def __init__(self, coordinator: YAWAMFDataUpdateCoordinator, ingress_token: str) -> None:
        self.coordinator = coordinator
        self.ingress_token = ingress_token

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
        if not _is_authorized_ingress_request(request, self.ingress_token):
            raise web.HTTPUnauthorized()

        target_url = _build_target_url(self.coordinator.url, path, _upstream_query_string(request))
        headers = _build_forward_headers(request.headers, self.coordinator.headers)
        body = None if request.method in {"GET", "HEAD"} else await request.read()
        should_set_cookie = request.query.get(_INGRESS_TOKEN_PARAM) == self.ingress_token

        try:
            async with self.coordinator.session.request(
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
                _set_ingress_cookie(response, self.ingress_token, should_set_cookie)

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
                    _set_ingress_cookie(text_response, self.ingress_token, should_set_cookie)
                    return text_response

                await response.prepare(request)

                if request.method != "HEAD":
                    async for chunk in upstream.content.iter_chunked(64 * 1024):
                        await response.write(chunk)

                await response.write_eof()
                return response
        except Exception as err:  # noqa: BLE001 - HA should return a proxy failure, not crash the view
            _LOGGER.exception("YA-WAMF ingress proxy request failed")
            raise web.HTTPBadGateway(text=f"YA-WAMF ingress proxy failed: {err}") from err


class YAWAMFIngressAssetView(HomeAssistantView):
    """Serve known YA-WAMF public assets at HA root for iframe compatibility."""

    requires_auth = False

    def __init__(self, coordinator: YAWAMFDataUpdateCoordinator, asset_path: str) -> None:
        self.coordinator = coordinator
        self.asset_path = asset_path
        self.url = f"/{asset_path}"
        self.name = f"api:yawamf:asset:{asset_path}"

    async def get(self, request: web.Request) -> web.StreamResponse:
        target_url = _build_target_url(self.coordinator.url, self.asset_path, _upstream_query_string(request))

        try:
            async with self.coordinator.session.request(
                "GET",
                target_url,
                headers=_build_forward_headers(request.headers, self.coordinator.headers),
                allow_redirects=False,
                timeout=ClientTimeout(total=None),
            ) as upstream:
                if _should_rewrite_response(upstream.headers):
                    body = await upstream.text()
                    response_headers = _response_headers(upstream.headers)
                    response_headers.pop("Content-Type", None)
                    return web.Response(
                        status=upstream.status,
                        reason=upstream.reason,
                        headers=response_headers,
                        text=_rewrite_root_paths(body),
                        content_type=upstream.content_type,
                        charset=upstream.charset,
                    )

                response = web.StreamResponse(
                    status=upstream.status,
                    reason=upstream.reason,
                    headers=_response_headers(upstream.headers),
                )
                await response.prepare(request)
                async for chunk in upstream.content.iter_chunked(64 * 1024):
                    await response.write(chunk)
                await response.write_eof()
                return response
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("YA-WAMF ingress asset request failed")
            raise web.HTTPBadGateway(text=f"YA-WAMF ingress asset failed: {err}") from err


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
        if lower in _HOP_BY_HOP_HEADERS or lower in _INGRESS_BLOCKED_RESPONSE_HEADERS or lower in {"content-length", "content-encoding"}:
            continue
        headers[key] = value
    return headers


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
    replacements = {
        'href="/': f'href="{INGRESS_URL}/',
        'src="/': f'src="{INGRESS_URL}/',
        'content="/': f'content="{INGRESS_URL}/',
        'url(/': f'url({INGRESS_URL}/',
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

    return rewritten


async def async_register_ingress(hass: HomeAssistant, coordinator: YAWAMFDataUpdateCoordinator) -> None:
    """Register the HA proxy view and sidebar panel."""
    ingress_token = secrets.token_urlsafe(32)
    hass.http.register_view(YAWAMFIngressView(coordinator, ingress_token))
    for asset_path in _PUBLIC_ASSET_PATHS:
        hass.http.register_view(YAWAMFIngressAssetView(coordinator, asset_path))

    try:
        from homeassistant.components import frontend

        frontend.async_register_built_in_panel(
            hass,
            component_name="iframe",
            sidebar_title="YA-WAMF",
            sidebar_icon="mdi:bird",
            frontend_url_path=PANEL_URL_PATH,
            config={"url": f"{INGRESS_URL}/?{_INGRESS_TOKEN_PARAM}={ingress_token}"},
            require_admin=False,
        )
    except Exception:  # noqa: BLE001 - proxy remains usable even if panel registration API differs
        _LOGGER.exception("Failed to register YA-WAMF Home Assistant sidebar panel")


async def async_unregister_ingress_panel(hass: HomeAssistant) -> None:
    """Best-effort removal of the sidebar panel on unload/reload."""
    try:
        from homeassistant.components import frontend

        remove_panel = getattr(frontend, "async_remove_panel", None)
        if remove_panel is not None:
            await remove_panel(hass, PANEL_URL_PATH)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Failed to unregister YA-WAMF sidebar panel", exc_info=True)
