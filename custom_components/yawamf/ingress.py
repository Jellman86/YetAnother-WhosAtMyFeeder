"""Home Assistant sidebar proxy for YA-WAMF."""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientTimeout, web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

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


class YAWAMFIngressView(HomeAssistantView):
    """Proxy authenticated Home Assistant requests to the configured YA-WAMF UI."""

    url = f"{INGRESS_URL}" + "/{path:.*}"
    name = "api:yawamf:ingress"
    requires_auth = True

    def __init__(self, coordinator: YAWAMFDataUpdateCoordinator) -> None:
        self.coordinator = coordinator

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
        target_url = _build_target_url(self.coordinator.url, path, request.query_string)
        headers = _build_forward_headers(request.headers, self.coordinator.headers)
        body = None if request.method in {"GET", "HEAD"} else await request.read()

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

                if request.method != "HEAD" and _should_rewrite_text_response(upstream.headers):
                    body = await upstream.text()
                    rewritten = _rewrite_root_paths(body)
                    response_headers = _response_headers(upstream.headers)
                    response_headers.pop("Content-Type", None)
                    return web.Response(
                        status=upstream.status,
                        reason=upstream.reason,
                        headers=response_headers,
                        text=rewritten,
                        content_type=upstream.content_type,
                        charset=upstream.charset,
                    )

                await response.prepare(request)

                if request.method != "HEAD":
                    async for chunk in upstream.content.iter_chunked(64 * 1024):
                        await response.write(chunk)

                await response.write_eof()
                return response
        except Exception as err:  # noqa: BLE001 - HA should return a proxy failure, not crash the view
            _LOGGER.exception("YA-WAMF ingress proxy request failed")
            raise web.HTTPBadGateway(text=f"YA-WAMF ingress proxy failed: {err}") from err


def _build_target_url(base_url: str, path: str, query_string: str) -> str:
    clean_base = base_url.rstrip("/")
    clean_path = path.lstrip("/")
    target = f"{clean_base}/{clean_path}" if clean_path else f"{clean_base}/"
    if query_string:
        target = f"{target}?{query_string}"
    return target


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


def _should_rewrite_text_response(upstream_headers: Any) -> bool:
    content_type = str(upstream_headers.get("Content-Type", "")).lower()
    return "text/html" in content_type


def _rewrite_root_paths(body: str) -> str:
    replacements = {
        'href="/': f'href="{INGRESS_URL}/',
        'src="/': f'src="{INGRESS_URL}/',
        'content="/': f'content="{INGRESS_URL}/',
        'url(/': f'url({INGRESS_URL}/',
    }
    rewritten = body
    for old, new in replacements.items():
        rewritten = rewritten.replace(old, new)
    return rewritten


async def async_register_ingress(hass: HomeAssistant, coordinator: YAWAMFDataUpdateCoordinator) -> None:
    """Register the HA proxy view and sidebar panel."""
    hass.http.register_view(YAWAMFIngressView(coordinator))

    try:
        from homeassistant.components import panel_custom

        await panel_custom.async_register_panel(
            hass,
            webcomponent_name="ha-panel-iframe",
            frontend_url_path=PANEL_URL_PATH,
            sidebar_title="YA-WAMF",
            sidebar_icon="mdi:bird",
            module_url=None,
            config={"url": f"{INGRESS_URL}/"},
            require_admin=False,
            embed_iframe=True,
        )
    except Exception:  # noqa: BLE001 - proxy remains usable even if panel registration API differs
        _LOGGER.exception("Failed to register YA-WAMF Home Assistant sidebar panel")


async def async_unregister_ingress_panel(hass: HomeAssistant) -> None:
    """Best-effort removal of the sidebar panel on unload/reload."""
    try:
        from homeassistant.components import panel_custom

        unregister = getattr(panel_custom, "async_unregister_panel", None)
        if unregister is not None:
            await unregister(hass, PANEL_URL_PATH)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Failed to unregister YA-WAMF sidebar panel", exc_info=True)
