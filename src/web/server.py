"""
Web UI server — pwnagotchi-style screen mirror + plugin pages + inbound webhooks.

Runs on aiohttp directly on the bot's existing asyncio event loop (no extra thread
or process — important on a 512 MB Pi Zero). Started from main.py's post_init only
when WEB_UI_ENABLED is set.

Routes:
    GET  /                       dashboard (live screen + status + plugin cards)
    GET  /ui                     latest screen frame as PNG (JS polls this ~1/s)
    GET  /status                 JSON status (level, xp, uptime, battery, plugins)
    GET  /plugins                plugin index
    GET  /plugins/<name>/<sub>   -> plugin.on_webhook(<sub>, request)
    POST /webhook/<name>         inbound trigger -> hooks (event_type="webhook")

Auth: if WEB_UI_AUTH_TOKEN is set, dashboard pages require it (query ?token=,
header X-Auth-Token, or cookie). Webhooks use the separate WEB_WEBHOOK_TOKEN.
"""

import asyncio
import html
import logging
import time

from aiohttp import web

from config import (
    BOT_NAME,
    SCREEN_PNG_PATH,
    WEB_UI_AUTH_TOKEN,
    WEB_UI_HOST,
    WEB_UI_PORT,
    WEB_WEBHOOK_TOKEN,
)
from web.plugins import get_plugin, get_plugins

log = logging.getLogger(__name__)

_START_TS = time.time()


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _uptime_str() -> str:
    secs = int(time.time() - _START_TS)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def _status_dict() -> dict:
    status = {"bot": BOT_NAME, "uptime": _uptime_str(), "plugins": list(get_plugins().keys())}
    try:
        from db.stats import get_level_progress
        status["level"] = get_level_progress()
    except Exception as e:
        log.debug("status: level unavailable: %s", e)
    try:
        from hardware.battery import read as battery_read
        reading = battery_read()
        if reading is not None:
            status["battery"] = {
                "percent": reading.percentage,
                "voltage": round(reading.voltage_v, 2),
                "state": reading.short(),
            }
    except Exception:
        pass  # battery HAT optional / not present
    return status


def _coerce_response(result) -> web.StreamResponse:
    """Turn a plugin's return value into an aiohttp response."""
    if isinstance(result, web.StreamResponse):
        return result
    if isinstance(result, dict):
        return web.json_response(result)
    if isinstance(result, tuple):
        body, status, ctype = (list(result) + [200, "text/html"])[:3]
        return web.Response(text=str(body), status=int(status), content_type=ctype)
    if isinstance(result, bytes):
        return web.Response(body=result, content_type="application/octet-stream")
    return web.Response(text=str(result), content_type="text/html")


def _page(title: str, body: str) -> web.Response:
    doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: ui-monospace, monospace; background:#111; color:#ddd; margin:0; padding:1.2rem; }}
  a {{ color:#7fd; }} h1,h2 {{ font-weight:600; }}
  .screen {{ image-rendering: pixelated; border:1px solid #333; background:#fff; max-width:100%; }}
  .card {{ background:#1b1b1b; border:1px solid #2a2a2a; border-radius:8px; padding:.8rem 1rem; margin:.6rem 0; }}
  .grid {{ display:flex; flex-wrap:wrap; gap:1rem; }}
  .muted {{ color:#888; font-size:.85rem; }}
  button {{ background:#2a2a2a; color:#ddd; border:1px solid #444; border-radius:6px; padding:.4rem .8rem; cursor:pointer; }}
</style></head><body>{body}</body></html>"""
    return web.Response(text=doc, content_type="text/html")


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------

async def handle_index(request: web.Request) -> web.Response:
    status = _status_dict()
    lvl = status.get("level") or {}
    lvl_line = ""
    if lvl:
        lvl_line = f"Lv{lvl.get('level','?')} {html.escape(str(lvl.get('title','')))} — {lvl.get('xp','?')} XP"
    batt = status.get("battery")
    batt_line = ""
    if isinstance(batt, dict) and batt.get("percent") is not None:
        batt_line = f" · 🔋 {batt.get('percent')}%"

    cards = []
    for name, plugin in get_plugins().items():
        title = html.escape(plugin.title or name)
        frag = ""
        try:
            frag = plugin.dashboard_card() or ""
        except Exception as e:
            frag = f"<span class='muted'>card error: {html.escape(str(e))}</span>"
        link = f" — <a href='/plugins/{html.escape(name)}/'>open</a>" if plugin.has_page() else ""
        cards.append(f"<div class='card'><b>{title}</b>{link}<div>{frag}</div></div>")
    cards_html = "".join(cards) or "<p class='muted'>No plugins loaded.</p>"

    body = f"""
<h1>🦞 {html.escape(BOT_NAME)}</h1>
<p class="muted">{lvl_line}{batt_line} · up {html.escape(status['uptime'])}
  · <a href="/status">/status</a> · <a href="/plugins">/plugins</a></p>
<img id="screen" class="screen" src="/ui" alt="screen" width="100%" style="max-width:760px">
<h2>Plugins</h2>
<div class="grid">{cards_html}</div>
<script>
  setInterval(function(){{
    document.getElementById('screen').src = '/ui?t=' + Date.now();
  }}, 1000);
</script>"""
    return _page(BOT_NAME, body)


async def handle_ui(request: web.Request) -> web.StreamResponse:
    if not SCREEN_PNG_PATH.exists():
        return web.Response(status=503, text="no screen frame yet")
    return web.FileResponse(
        SCREEN_PNG_PATH,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


async def handle_status(request: web.Request) -> web.Response:
    return web.json_response(_status_dict())


async def handle_plugins(request: web.Request) -> web.Response:
    items = []
    for name, plugin in get_plugins().items():
        title = html.escape(plugin.title or name)
        desc = html.escape(plugin.description or "")
        if plugin.has_page():
            items.append(f"<li><a href='/plugins/{html.escape(name)}/'>{title}</a> <span class='muted'>{desc}</span></li>")
        else:
            items.append(f"<li>{title} <span class='muted'>{desc}</span></li>")
    body = f"<h1>Plugins</h1><p><a href='/'>&larr; back</a></p><ul>{''.join(items) or '<li>None</li>'}</ul>"
    return _page("Plugins", body)


async def handle_plugin_page(request: web.Request) -> web.StreamResponse:
    name = request.match_info["name"]
    tail = request.match_info.get("tail", "")
    plugin = get_plugin(name)
    if plugin is None:
        return web.Response(status=404, text=f"no such plugin: {name}")
    if not plugin.has_page():
        return web.Response(status=404, text=f"plugin '{name}' has no page")
    try:
        result = plugin.on_webhook(tail, request)
        if asyncio.iscoroutine(result):
            result = await result
    except Exception as e:
        log.error("plugin %s page error: %s", name, e)
        return web.Response(status=500, text=f"plugin error: {e}")
    return _coerce_response(result)


async def handle_webhook(request: web.Request) -> web.Response:
    """Inbound trigger -> hooks system. Secured by WEB_WEBHOOK_TOKEN."""
    if not WEB_WEBHOOK_TOKEN:
        return web.Response(status=404, text="webhooks disabled (set WEB_WEBHOOK_TOKEN)")
    token = request.query.get("token") or request.headers.get("X-Webhook-Token", "")
    if token != WEB_WEBHOOK_TOKEN:
        return web.Response(status=401, text="unauthorized")

    name = request.match_info["name"]
    payload: dict = {}
    if request.can_read_body:
        try:
            payload = await request.json()
        except Exception:
            payload = {"raw": (await request.text())[:4000]}
    if not isinstance(payload, dict):
        payload = {"payload": payload}

    from hooks.runner import run_hook, HookEvent
    event = run_hook(HookEvent(
        event_type="webhook",
        action=name,
        text=str(payload)[:500],
        data={"payload": payload, "query": dict(request.query)},
    ))
    log.info("Webhook '%s' fired (%d hook message(s) queued)", name, len(event.messages))
    return web.json_response({"ok": True, "webhook": name, "queued_messages": len(event.messages)})


# ----------------------------------------------------------------------------
# Auth middleware
# ----------------------------------------------------------------------------

@web.middleware
async def _auth_middleware(request: web.Request, handler):
    # Webhooks carry their own token and bypass dashboard auth.
    if request.path.startswith("/webhook/") or not WEB_UI_AUTH_TOKEN:
        return await handler(request)

    token = (
        request.query.get("token")
        or request.headers.get("X-Auth-Token")
        or request.cookies.get("ocg_token")
    )
    if token != WEB_UI_AUTH_TOKEN:
        return web.Response(status=401, text="Unauthorized — append ?token=YOUR_TOKEN")

    resp = await handler(request)
    # Persist a token supplied via query string so links/navigation keep working.
    if request.query.get("token") == WEB_UI_AUTH_TOKEN:
        resp.set_cookie("ocg_token", WEB_UI_AUTH_TOKEN, max_age=86400, httponly=True, samesite="Lax")
    return resp


# ----------------------------------------------------------------------------
# Lifecycle
# ----------------------------------------------------------------------------

def build_app() -> web.Application:
    app = web.Application(middlewares=[_auth_middleware])
    app.add_routes([
        web.get("/", handle_index),
        web.get("/ui", handle_ui),
        web.get("/status", handle_status),
        web.get("/plugins", handle_plugins),
        web.get(r"/plugins/{name}/{tail:.*}", handle_plugin_page),
        web.post(r"/webhook/{name}", handle_webhook),
    ])
    return app


async def start_web_server():
    """Start the web server on the running event loop. Returns the AppRunner (keep a reference)."""
    runner = web.AppRunner(build_app())
    await runner.setup()
    site = web.TCPSite(runner, WEB_UI_HOST, WEB_UI_PORT)
    await site.start()
    log.info("Web UI available at http://%s:%d/", WEB_UI_HOST, WEB_UI_PORT)
    return runner
