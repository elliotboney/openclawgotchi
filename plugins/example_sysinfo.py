"""
Example plugin: sysinfo.

Demonstrates the full web-plugin API:
  - dashboard_card(): an HTML fragment shown on the main dashboard
  - on_webhook(path, request): serves pages under /plugins/sysinfo/
  - on_heartbeat(event): auto-bridged into the hooks system (fires every heartbeat)

Copy this file to .workspace/plugins/ (per-bot) or plugins/ (project) and toggle the
web UI on with WEB_UI_ENABLED=1 to see it. Keep plugins light — this runs on a Pi Zero.
"""

import html
import time

from web.plugins import Plugin


class SysInfoPlugin(Plugin):
    name = "sysinfo"
    title = "System Info"
    description = "Uptime, load, and recent audit events."

    def on_loaded(self):
        self.loaded_at = time.time()
        self.heartbeats = 0

    # --- dashboard card (shown inline on "/") ---
    def dashboard_card(self):
        load = self._loadavg()
        return f"<span class='muted'>load {load} · heartbeats seen: {self.heartbeats}</span>"

    # --- page at /plugins/sysinfo/<path> ---
    def on_webhook(self, path, request):
        if path.strip("/") == "events.json":
            return {"recent": self._recent_events(limit=20)}

        rows = "".join(
            f"<li class='muted'>{html.escape(line)}</li>" for line in self._recent_events(limit=25)
        ) or "<li class='muted'>no events yet</li>"
        return f"""
        <h1>System Info</h1>
        <p><a href="/">&larr; back</a> · <a href="/plugins/sysinfo/events.json">events.json</a></p>
        <p>load average: <b>{self._loadavg()}</b></p>
        <h2>Recent audit events</h2>
        <ul>{rows}</ul>
        """

    # --- event hook (auto-registered via the bridge) ---
    def on_heartbeat(self, event):
        self.heartbeats += 1

    # --- helpers ---
    def _loadavg(self):
        try:
            import os
            return ", ".join(f"{x:.2f}" for x in os.getloadavg())
        except Exception:
            return "n/a"

    def _recent_events(self, limit=20):
        """Tail the audit trail if present — best-effort, no hard dependency."""
        try:
            from config import PROJECT_DIR
            log_path = PROJECT_DIR / "logs" / "commands.jsonl"
            if not log_path.exists():
                return []
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-limit:]
            return [ln.strip() for ln in lines if ln.strip()]
        except Exception:
            return []
