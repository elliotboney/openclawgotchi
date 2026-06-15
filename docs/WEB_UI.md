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

    def on_ui_render(self, ui):               # optional: draw on the E-Ink screen
        ui.text((ui.width - 30, ui.content_top), "hi")

    def on_heartbeat(self, event):            # optional: auto-bridged into the hooks system
        ...
```

- Define `on_webhook` to get a clickable page at `/plugins/<name>/`; omit it for a card-only plugin.
- `on_webhook` may be a coroutine.
- Event methods (`on_startup`, `on_message`, `on_command`, `on_heartbeat`) are auto-registered
  as hooks, so plugins receive the same events as `hooks/`.

See `plugins/example_sysinfo.py` for a complete working plugin.

## Drawing on the E-Ink screen (`on_ui_render`)

This is the pwnagotchi-style superpower that skills can't have: a plugin can **add elements
to the actual display**. Implement `on_ui_render(self, ui)`; it runs on every frame inside the
**display render subprocess** (so a buggy plugin can't crash the bot — only its own overlay
is dropped).

```python
def on_ui_render(self, ui):
    clock = time.strftime("%H:%M")
    w, _ = ui.measure(clock)
    ui.text((ui.width - w - 3, ui.content_top), clock)   # top-right corner
```

**It's additive and non-destructive.** Everything you draw lands on a separate overlay that
is merged with a "darken" composite — your ink fills *blank* pixels but can **never erase**
the core face, name, or status. You append; you can't clobber. (This is stronger than
pwnagotchi, which only relies on you picking free coordinates.)

The `ui` object (a `UIContext`) provides:

| Member | Purpose |
|---|---|
| `ui.width`, `ui.height` | Panel size (250×122) |
| `ui.header_h`, `ui.footer_h` | Reserved core bands (14 px each) |
| `ui.content_top`, `ui.content_bottom` | Safe vertical range for plugin elements |
| `ui.variant_b` | True on the 3-colour (B) panel |
| `ui.ctx` | Read-only dict: `mood`, `status_text`, `level`, `battery` |
| `ui.font`, `ui.font_big` | Small UI font / bubble font |
| `ui.text(pos, value)` | Draw text |
| `ui.label(pos, label, value)` | Draw `"label value"` (pwnagotchi LabeledValue style) |
| `ui.rect(box)`, `ui.line(xy)` | Primitives |
| `ui.measure(value)` | `(w, h)` of text, for right/centre alignment |
| `ui.blit(img, pos)` | Paste a 1-bit icon |

Keep `on_ui_render` cheap — it runs in the render path on a Pi Zero. The face is the main
content; the top-right and the gaps beside it are the usual spots for a small widget.

## Notes & limits

- Keep plugins light — they share the Pi Zero's ~512 MB. Heavy work belongs elsewhere.
- The dashboard's control actions are read-only by design; no remote shutdown/reboot is
  exposed (the bot already manages itself via Telegram and `manage_service`).
- Disable instantly with `WEB_UI_ENABLED=0` and a restart.
