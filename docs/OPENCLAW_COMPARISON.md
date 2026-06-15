# OpenClaw vs. OpenClawGotchi — Feature Comparison

A side-by-side comparison of the upstream **OpenClaw** project (Peter Steinberger's
open-source personal AI agent, formerly Clawdbot/Moltbot — MIT, ~68k★) and
**OpenClawGotchi**, our Raspberry Pi Zero 2W (512 MB RAM) E-Ink port.

The goal of this doc is honest: show what carried over, what got cut, and — for each
cut — whether it was **genuinely forced by the hardware** or just **not built yet**
(i.e. reclaimable on the Pi without risking an OOM).

> TL;DR: The *soul* of OpenClaw survived the port — SKILL.md skills, markdown memory,
> a heartbeat, self-modification, model-agnostic routing. What got dropped is mostly
> the **breadth**: 23+ messaging channels → 2, the web Control UI, companion apps,
> sandboxing, and event-driven triggers (webhooks/cron-from-outside). A meaningful
> chunk of that breadth is **network I/O, not RAM**, and could come back cheaply.

---

## Main feature comparison

Legend: ✅ full · 🟡 partial / reduced · ❌ absent · ➕ Gotchi-only addition

| Feature area | OpenClaw (upstream) | OpenClawGotchi (ours) | Verdict on the gap |
|---|---|---|---|
| **Messaging channels** | ✅ 23–50+ (WhatsApp, Telegram, Slack, Discord, Signal, iMessage, IRC, Teams, Matrix, LINE, Feishh, etc.) | 🟡 2 — Telegram (primary/required) + Discord (optional inbound) | Mostly **reclaimable** — channels are network I/O, not RAM. Each adds maintenance, not memory pressure. |
| **Control plane / Web UI** | ✅ Local gateway + Control UI dashboard, WebSocket API (port 18789), WebChat debug | 🟡 Telegram *is* the control plane; no web UI | Reclaimable-ish — a tiny status page is light; a full dashboard is scope, not RAM. |
| **Companion apps** | ✅ Windows Hub, macOS menu-bar, iOS/Android nodes over WebSocket | ➕ Replaced by **physical E-Ink "body"** (faces/moods/status) | Different philosophy — the hardware *is* the companion. Not a loss. |
| **Skills (SKILL.md)** | ✅ 100+ via ClawHub registry, installable | 🟡 10 active + reference catalog (`openclaw-skills/`), **RAM-gated** via `CORE_SKILLS`/`ACTIVE_SKILLS` | **Hardware-justified** — parsing every skill into context is the OOM risk. Catalog-search keeps breadth without the RAM. |
| **Self-improvement** | ✅ Autonomously writes new skills/code | 🟡 Self-*modifies* own source (`write_file` + `check_syntax` + `safe_restart`); can write skills but isn't pushed to | **Reclaimable** — it's prompting/encouragement, not hardware. |
| **Memory** | ✅ Markdown + YAML, git-backupable, grep-able | ✅ SQLite (FTS5) **+** daily markdown logs **+** Obsidian vault | At parity / arguably **richer** (vault + dreaming + crystallization). |
| **Heartbeat / autonomy** | ✅ Daemon, **~30 min** default; reads `HEARTBEAT.md` | 🟡 **4 h** default; dreaming + crystallization + mood + XP | **Hardware-justified** — every beat is an LLM call (cost/heat/RAM churn). Interval is config, not a wall. |
| **External triggers** | ✅ Webhooks, cron, **Gmail Pub/Sub** push | 🟡 Internal cron scheduler only; no inbound webhooks | **Reclaimable** — a small aiohttp listener is light. This is a real autonomy gap. |
| **Model providers** | ✅ Model-agnostic (Anthropic/OpenAI/Google/Ollama), **auth rotation + fallback chains** | 🟡 Lite: glm / gemini / ollama · Pro: `claude` CLI. No rotation/fallback chains | Routing logic is ~free on RAM — **reclaimable** and would improve reliability. |
| **Sandboxing** | ✅ Configurable Docker / SSH / OpenShell backends | ❌ No sandbox — relies on shell guards (`DANGEROUS_COMMANDS`, `DISALLOWED_SHELL_TOKENS`, `BLOCKED_EXECUTABLES`, `PROTECTED_FILES`) | **Hardware-justified** — Docker would OOM a Pi Zero instantly. Guards are the deliberate trade-off. |
| **Voice — input** | ✅ Wake-word (mac/iOS), continuous (Android) | 🟡 Whisper transcription of voice messages (no wake-word, no always-on mic) | Partly hardware (no always-on audio DSP), partly scope. |
| **Voice — output (TTS)** | ✅ ElevenLabs + system fallback | ❌ None (E-Ink `SAY:` is a *visual* speech bubble) | **Reclaimable** — TTS is an API call; gated only by having a speaker. |
| **Image / vision** | ✅ Image understanding | ✅ OpenAI Vision (`gpt-4o-mini`) | At parity. |
| **Documents / PDF** | ✅ Documents | ✅ Text-PDF + text docs inline (no OCR of scanned PDFs) | Near parity. |
| **Browser / computer automation** | ✅ First-class browser control, canvas, nodes | ❌ None | **Hardware-justified** — Chromium/Playwright won't fit in 512 MB. |
| **Web search** | ✅ (via skills/tools) | ❌ No web-search tool | **Reclaimable** — a search API call is lightweight (no browser needed). Notable miss. |
| **Email** | ✅ Read/send | ❌ Referenced in examples, **not wired** | **Reclaimable** — IMAP/SMTP is just network I/O. High value. |
| **Calendar** | ✅ (skills) | ❌ | Reclaimable (API). |
| **MCP (Model Context Protocol)** | 🟡 Not clearly documented upstream | ❌ None | Roughly even; both thin here. |
| **Audit / safety logging** | 🟡 Tool policies + approvals | ✅ Append-only audit trail (`command_logger`) + hooks | Gotchi arguably **stronger** here. |
| **Hooks system** | ✅ Event hooks | ✅ startup/message/command/heartbeat hooks (`.workspace/hooks/`) | At parity. |
| **Inter-bot mail (`MAIL:`)** | n/a | ❌ In CHANGELOG history but **not implemented** now | Was a "Senior Brother" link to OpenClaw-on-Mac; currently dead. |
| **E-Ink display / persona** | ❌ | ➕ Waveshare 2.13" V4, 35+ kaomoji moods, control tags (`FACE:`/`SAY:`/`DISPLAY:`/`DM:`), auto-mood | **Gotchi-only** — the whole point of the port. |
| **XP / leveling** | ❌ | ➕ Lv1→20+ with XP from messages/vault/cron/heartbeat | Gotchi-only flavor. |
| **Battery / UPS monitoring** | ❌ | ➕ Waveshare UPS HAT (INA219) / PiSugar 2 | Gotchi-only (portable Pi). |

---

## "Was too much cut out?" — the honest read

Your instinct is partly right. Splitting the cuts into two buckets:

### Genuinely forced by the hardware (correct calls — leave them cut)
- **Docker/SSH sandboxing** — would OOM a 512 MB Pi. Shell guards are the right substitute.
- **Browser/computer automation** — Chromium can't run here.
- **Loading all 100+ skills into context** — RAM-gating + catalog search is the correct design.
- **Always-on voice / wake-word** — no audio DSP headroom.
- **30-min heartbeat** — 4 h is a reasonable cost/heat/RAM concession (and it's just config).

### Cut but **not** really a hardware problem (reclaimable on the Pi Zero)
These are mostly **network I/O or pure logic** — they cost startup imports and a few KB, not the hundreds of MB that crash the device. This is where "too much was cut" actually holds:

1. **Web search** — a single search-API tool (no browser). High value, low RAM.
2. **Email (IMAP/SMTP)** — already implied by the README, never wired. Just network.
3. **Inbound webhooks / external triggers** — a tiny aiohttp listener restores OpenClaw's
   event-driven autonomy (the "acts without you prompting" promise).
4. **Model fallback chains + auth rotation** — pure routing logic; improves reliability for free.
5. **TTS output** — an API call; only real dependency is a speaker.
6. **Autonomous skill-writing** — the `coding` skill + `write_file` already make this *possible*;
   it just isn't encouraged in the prompt. No code needed, only nudging.
7. **More lightweight channels** (Signal/Matrix/WhatsApp bridges) — network, not memory,
   though each adds maintenance surface.

### Suggested priority if you want to "uncut"
**Web search → email → inbound webhooks → model fallback chains.** All four are RAM-cheap,
each restores a headline OpenClaw capability, and none threaten the OOM budget. Skill
lazy-loading already proves the pattern: keep the *gate* (don't import until used), and you
can add capability without adding resident memory.

---

## Sources

- [OpenClaw on GitHub](https://github.com/openclaw/openclaw)
- [What Is OpenClaw? (Milvus)](https://milvus.io/blog/openclaw-formerly-clawdbot-moltbot-explained-a-complete-guide-to-the-autonomous-ai-agent.md)
- [What is OpenClaw? (DigitalOcean)](https://www.digitalocean.com/resources/articles/what-is-openclaw)
- OpenClawGotchi codebase (this repo) — see `CLAUDE.md`, `src/llm/litellm_connector.py`,
  `src/skills/loader.py`, `src/bot/heartbeat.py`, `src/config.py`.
