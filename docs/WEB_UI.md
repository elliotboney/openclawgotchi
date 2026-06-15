# Web UI — screen mirror, plugins & webhooks

A pwnagotchi-inspired web interface for OpenClawGotchi: see the live E-Ink screen in a
browser, extend it with plugins, and trigger the bot from external events via webhooks.

It is **off by default** and built to respect the Pi Zero's RAM budget: a single
[aiohttp](https://docs.aiohttp.org/) server runs on the bot's existing event loop (no
extra thread or process), and nothing is imported until you turn it on.

> ⚠️ **No sandbox.** The bot runs on bare metal. Only expose the web UI on a trusted
> LAN or a private overlay (Tailscale/WireGuard), and set a token. Don't port-forward it.

## Enable it

```bash
# .env
WEB_UI_ENABLED=1
WEB_UI_HOST=0.0.0.0          # 127.0.0.1 for localhost-only (reach it via SSH tunnel)
WEB_UI_PORT=8080
WEB_UI_AUTH_TOKEN=changeme   # dashboard requires ?token=changeme
WEB_WEBHOOK_TOKEN=s3cr3t     # required to use POST /webhook/<name>
```

Then `pip install -r requirements.txt` (adds `aiohttp`) and restart. Open
`http://<pi-ip>:8080/?token=changeme` — the token is then stored in a cookie.

## Routes

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Dashboard: live screen + status + plugin cards |
| `/ui` | GET | Latest screen frame as PNG (the page polls this ~1×/sec) |
| `/status` | GET | JSON: bot, level/XP, uptime, battery, plugins |
| `/plugins` | GET | Plugin index |
| `/plugins/<name>/<sub>` | GET | Routed to that plugin's `on_webhook(sub, request)` |
| `/webhook/<name>` | POST | Inbound trigger → hooks (`event_type="webhook"`) |

### The live screen

`src/ui/gotchi_ui.py` writes a PNG snapshot of every rendered frame to `data/screen.png`
(atomic write, upscaled by `WEB_UI_SCREEN_SCALE`). `/ui` serves that file. Because the
renderer only runs on real display updates (the E-Ink panel is slow and dedup'd), browser
polling never forces an expensive re-render — it just re-fetches the latest frame. This
also works on a dev machine with no panel attached.

## Webhooks (external triggers)

```bash
curl -X POST "http://<pi-ip>:8080/webhook/deploy?token=s3cr3t" \
     -H 'Content-Type: application/json' -d '{"status":"ok"}'
```

The request fires a `HookEvent(event_type="webhook", action="deploy", data={"payload": ...})`
through the existing hooks system. Add a handler in `hooks/` or `.workspace/hooks/`:

```python
from hooks.runner import hook

@hook("webhook")
def on_webhook(event):
    if event.action == "deploy":
        # event.data["payload"] holds the JSON body
        ...
```

## Writing a plugin

Drop a `.py` file in `plugins/` (project) or `.workspace/plugins/` (per-bot, wins on name
clash). Subclass `Plugin`; the web contract mirrors pwnagotchi (`on_webhook(self, path, request)`).

```python
from web.plugins import Plugin

class HelloPlugin(Plugin):
    name = "hello"
    title = "Hello"
    description = "A tiny example."

    def on_loaded(self):
        ...                                   # one-time setup

    def dashboard_card(self):
        return "<b>hi there</b>"             # optional inline card on "/"

    def on_webhook(self, path, request):      # serves /plugins/hello/<path>
        return "<h1>my page</h1>"            # return str (HTML), dict (JSON), or (body, status, ctype)

    def on_heartbeat(self, event):            # optional: auto-bridged into the hooks system
        ...
```

- Define `on_webhook` to get a clickable page at `/plugins/<name>/`; omit it for a card-only plugin.
- `on_webhook` may be a coroutine.
- Event methods (`on_startup`, `on_message`, `on_command`, `on_heartbeat`) are auto-registered
  as hooks, so plugins receive the same events as `hooks/`.

See `plugins/example_sysinfo.py` for a complete working plugin.

## Notes & limits

- Keep plugins light — they share the Pi Zero's ~512 MB. Heavy work belongs elsewhere.
- The dashboard's control actions are read-only by design; no remote shutdown/reboot is
  exposed (the bot already manages itself via Telegram and `manage_service`).
- Disable instantly with `WEB_UI_ENABLED=0` and a restart.
