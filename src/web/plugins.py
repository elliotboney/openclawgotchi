"""
Web UI plugin system — pwnagotchi-style.

A Plugin is a small Python class discovered from `.workspace/plugins/` (per-bot,
highest precedence) then `plugins/` (project). Plugins extend the web server with
their own pages and can react to bot events.

The web contract mirrors pwnagotchi so existing knowledge transfers:

    class MyPlugin(Plugin):
        name = "myplugin"
        title = "My Plugin"          # shown on the dashboard

        def on_loaded(self):
            ...                       # called once at startup

        def dashboard_card(self):
            return "<p>hello</p>"    # optional HTML fragment for the index page

        def on_webhook(self, path, request):
            # serves /plugins/myplugin/<path>; return str (HTML) / dict (JSON) / tuple
            return "<h1>my page</h1>"

Optional event methods (on_message / on_heartbeat / on_command / on_startup) are
auto-bridged into src/hooks so plugins receive the same events as hooks.

Everything here is intentionally lightweight and lazy — nothing imports aiohttp,
and discovery is skipped entirely when the web UI is disabled.
"""

import logging
import importlib.util
from pathlib import Path
from typing import Any, Optional

from config import PROJECT_DIR, WORKSPACE_DIR

log = logging.getLogger(__name__)

# Discovery order (first wins on name collision), mirroring the hooks system.
PLUGIN_DIRS = [
    WORKSPACE_DIR / "plugins",
    PROJECT_DIR / "plugins",
]

# Event methods that are bridged into the hooks system if a plugin defines them.
_EVENT_BRIDGE = {
    "on_startup": "startup",
    "on_message": "message",
    "on_command": "command",
    "on_heartbeat": "heartbeat",
}


class Plugin:
    """Base class for web UI plugins. Subclass and set `name`."""

    name: str = "unnamed"
    title: str = ""          # human label for the dashboard; falls back to name
    description: str = ""

    def on_loaded(self) -> None:
        """Called once when the plugin is loaded. Override for setup."""

    def on_unload(self) -> None:
        """Called on shutdown. Override for cleanup."""

    def dashboard_card(self) -> Optional[str]:
        """Return an HTML fragment shown on the dashboard, or None for no card."""
        return None

    def on_ui_render(self, ui: Any) -> None:
        """
        Draw extra elements on the E-Ink screen (pwnagotchi-style, additive).

        Runs inside the display render subprocess on every frame. `ui` is a UIContext
        exposing text()/label()/rect()/line()/measure()/blit(), layout metrics
        (width/height/content_top/content_bottom), and ui.ctx (mood, status, level,
        battery). Whatever you draw is merged non-destructively — you can add ink to
        blank areas but cannot erase the core face/name/status. Keep it cheap.
        """

    def has_page(self) -> bool:
        """Whether this plugin exposes a clickable page at /plugins/<name>/."""
        return type(self).on_webhook is not Plugin.on_webhook

    def has_ui(self) -> bool:
        """Whether this plugin draws on the E-Ink screen."""
        return type(self).on_ui_render is not Plugin.on_ui_render

    def on_webhook(self, path: str, request: Any) -> Any:
        """
        Serve /plugins/<name>/<path>. `request` is the aiohttp Request.
        Return one of: str (HTML), dict (JSON), or (body, status, content_type).
        Default: not implemented.
        """
        return ("Not found", 404, "text/plain")


# Loaded plugin instances, keyed by name (insertion order = load order).
_plugins: dict[str, Plugin] = {}


def _bridge_events(plugin: Plugin) -> None:
    """Register any event methods the plugin defines as hooks."""
    from hooks.runner import register_hook

    for method_name, event_type in _EVENT_BRIDGE.items():
        if type(plugin).__dict__.get(method_name) or _defines(plugin, method_name):
            handler = getattr(plugin, method_name)
            register_hook(event_type, handler)
            log.debug("Plugin %s bridged %s -> %s hook", plugin.name, method_name, event_type)


def _defines(plugin: Plugin, method_name: str) -> bool:
    """True if the plugin's class (not Plugin base) defines method_name."""
    return any(
        method_name in klass.__dict__
        for klass in type(plugin).__mro__
        if klass is not Plugin and klass is not object
    )


def _load_plugins_from_file(path: Path) -> int:
    """Import a plugin file and instantiate every Plugin subclass it defines."""
    count = 0
    try:
        spec = importlib.util.spec_from_file_location(f"plugin_{path.stem}", path)
        if not (spec and spec.loader):
            return 0
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, Plugin)
                and attr is not Plugin
            ):
                instance = attr()
                if instance.name in _plugins:
                    continue  # earlier dir (higher precedence) already provided this name
                try:
                    instance.on_loaded()
                except Exception as e:
                    log.error("Plugin %s on_loaded failed: %s", instance.name, e)
                _bridge_events(instance)
                _plugins[instance.name] = instance
                count += 1
                log.info("Loaded plugin: %s", instance.name)
    except Exception as e:
        log.error("Failed to load plugins from %s: %s", path.name, e)
    return count


def discover_and_load_plugins() -> dict[str, Plugin]:
    """Discover and load all plugins from the plugin directories."""
    for plugin_dir in PLUGIN_DIRS:
        if not plugin_dir.exists():
            continue
        for path in sorted(plugin_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            _load_plugins_from_file(path)
    if _plugins:
        log.info("Loaded %d plugin(s) total", len(_plugins))
    return _plugins


def get_plugins() -> dict[str, Plugin]:
    """Return the loaded plugins (name -> instance)."""
    return _plugins


def get_plugin(name: str) -> Optional[Plugin]:
    return _plugins.get(name)


def discover_render_plugins() -> list:
    """
    Load plugins that draw on the screen, for use inside the display render subprocess.

    Deliberately lightweight and separate from discover_and_load_plugins(): it does NOT
    register event hooks (the subprocess has no bot loop), only instantiates plugins that
    override on_ui_render and calls on_loaded() best-effort. Returns a fresh list each call.
    """
    instances: list = []
    seen: set = set()
    for plugin_dir in PLUGIN_DIRS:
        if not plugin_dir.exists():
            continue
        for path in sorted(plugin_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"render_{path.stem}", path)
                if not (spec and spec.loader):
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for attr in vars(module).values():
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, Plugin)
                        and attr is not Plugin
                        and attr.on_ui_render is not Plugin.on_ui_render
                    ):
                        instance = attr()
                        if instance.name in seen:
                            continue
                        try:
                            instance.on_loaded()
                        except Exception as e:
                            log.debug("render plugin %s on_loaded: %s", instance.name, e)
                        seen.add(instance.name)
                        instances.append(instance)
            except Exception as e:
                log.error("Failed to load render plugin from %s: %s", path.name, e)
    return instances
