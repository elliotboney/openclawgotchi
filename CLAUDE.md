# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

OpenClawGotchi is a single-process Python Telegram bot that runs an agentic AI "pet" on a Raspberry Pi Zero 2W (512 MB RAM) with a Waveshare 2.13" E-Ink display. Every design choice is constrained by that hardware: lazy imports, narrow context windows, skill gating, and crash-avoidance ("if I think too hard, I OOM"). Keep changes small and memory-conscious — heavy work (Docker, Rust builds, large logs) is intentionally out of scope and will crash the device.

## Run / develop / deploy

```bash
# Local dev run (reads .env via python-dotenv, override=True)
python3 src/main.py                 # entry point; requires TELEGRAM_BOT_TOKEN

# First-time Pi setup (creates venv --system-site-packages, installs deps,
# writes /etc/systemd/system/gotchi-bot.service, configures sudoers, starts service)
./setup.sh

# On the Pi, the bot runs as a systemd service:
sudo systemctl restart gotchi-bot     # restart
sudo systemctl status gotchi-bot      # status
journalctl -u gotchi-bot -f           # live logs

# Health check (also exposed as the health_check tool / /health command)
python3 src/utils/doctor.py

./harden.sh    # optional Pi security hardening
./sync.sh      # vault sync helper
```

There is **no test suite** and **no linter config**. Verify changes by running the bot and exercising flows over Telegram, or by running `doctor.py`. `python3 -c "import ast; ast.parse(open('file.py').read())"` (the same idea as the `check_syntax` tool) is the cheapest correctness gate before a restart.

Dependencies: `pip install -r requirements.txt`. On the Pi, GPIO/SPI libs (`RPi.GPIO`, `spidev`, `lgpio`) come from system site-packages, not pip — that's why the venv is created with `--system-site-packages`.

## Architecture (the big picture)

### Entry + event loop
`src/main.py` builds a `python-telegram-bot` `Application`, registers command + message handlers, schedules the heartbeat (every 4h), starts the cron scheduler, optionally starts the Discord inbound adapter in a background thread, and runs long-polling. On first run it copies `templates/` → `.workspace/` (the bot's mutable "mind", gitignored).

### The two-brain LLM router
`src/llm/router.py` (`get_router()`, global singleton) routes every model call to one of two connectors based on a `force_lite` flag:
- **Lite mode (default):** `LiteLLMConnector` — full tool-calling agent loop via LiteLLM. Backend chosen by `DEFAULT_LITE_PRESET` (`glm` = Z.ai Anthropic-compatible, `gemini`, or `ollama`; see `LLM_PRESETS` in `config.py`).
- **Pro mode:** `ClaudeConnector` — shells out to the `claude` CLI (`claude -p --dangerously-skip-permissions`) with `cwd=.workspace/`, so Claude reads `BOT_INSTRUCTIONS.md` itself. No fallback in Pro mode; rate limits bubble up. Toggle with `/pro`.

The router exposes `.lock` (Claude's asyncio lock) for busy-checks. `RateLimitError` is tracked in `src/llm/rate_limits.py`.

### The Lite-mode tool loop (the real agent)
`src/llm/litellm_connector.py` (~1500 lines) is the heart of the bot. It defines `TOOLS` (OpenAI-style function schemas) and `TOOL_MAP` (name → Python callable), then runs an iterative tool-call loop up to `MAX_TOOL_CALLS` (config). Tools cover shell, files, memory, skills, scheduling, git, service control, and the Obsidian vault. **Safety guards live here and are load-bearing** — `DANGEROUS_COMMANDS`, `DISALLOWED_SHELL_TOKENS` (no pipes/redirection/chaining), `BLOCKED_EXECUTABLES` (no sudo/su), and `PROTECTED_FILES` (`.env`, `gotchi.db`, `src/drivers/`, `src/ui/`). Preserve these when editing tool code.

Handlers can restrict which tools the model sees via `allowed_tool_names` (e.g. "memo mode" narrows to memory tools) — see `_allowed_tool_names_for_mode` and `_filter_tools`.

### System prompt assembly (lazy, RAM-driven)
`src/llm/prompts.py::build_system_context(user_message)` composes the prompt and **lazy-loads** heavy sections only when the message seems to need them (`needs_extra_context`): ARCHITECTURE, TOOLS, SOUL/IDENTITY, VAULT. Always included: bot instructions, language directive, custom faces, eligible skills, memory context, and retrieval context. This keeps the prompt small to avoid OOM. The persona/identity files (`SOUL.md`, `IDENTITY.md`, `BOT_INSTRUCTIONS.md`) live in `.workspace/` and the bot can rewrite them with `write_file` to "evolve."

### Hardware display via subprocess
The model emits inline control tags in its text — `FACE: <mood>`, `SAY: <msg>`, `DISPLAY: <text>`, `DM: <msg>`. `src/hardware/display.py::parse_and_execute_commands(response)` strips those tags out of the user-facing reply and drives the E-Ink screen by spawning `src/ui/gotchi_ui.py` as a **separate process** (`_run_display_update`) — isolating the fragile Pillow/SPI rendering from the main loop so a render crash can't take down the bot. 25+ kaomoji moods in `src/ui/faces.py`; custom faces persist in `data/custom_faces.json`.

### Skills (gated, OpenClaw-style)
`src/skills/loader.py` reads `SKILL.md` frontmatter from `gotchi-skills/` (active, takes precedence) and `openclaw-skills/` (reference catalog, read-only, often macOS-only). Skills are **gated** by `SkillRequirements` (required bins, env vars, OS). To save RAM, only skills in `CORE_SKILLS` + `ACTIVE_SKILLS` env are parsed at all. The model discovers skills through the prompt and reads `SKILL.md` on demand via `read_skill`/`search_skills`.

### Memory: three layers
1. **SQLite** (`gotchi.db`, `src/db/memory.py`): `messages` (rolling history, auto-pruned to ~50/chat), `facts` (FTS5 full-text long-term memory), `feedback_events`, `conversation_state`, `user_info`, `pending_tasks`. Stats/XP in `src/db/stats.py`.
2. **Daily logs** (`.workspace/memory/YYYY-MM-DD.md`) via `src/memory/` (`summarize.py`, `flush.py`, `knowledge.py`).
3. **Knowledge vault** (`.workspace/knowledge/`, Obsidian-compatible) via `src/memory/vault.py` — YAML frontmatter, wikilinks, retrieval-aware. The `vault_*` tools and `scripts/vault_*.py` operate here. The heartbeat runs a conservative `dreaming` pass that captures at most a couple of clearly-missed notes; it never does mass cleanup/renames.

### Other subsystems
- `src/bot/handlers.py` (~1800 lines): all command handlers + the main `handle_message` pipeline (classification, memo mode, answer-first heuristics, continuity), plus voice (Whisper), photo/image (OpenAI Vision), and document/PDF ingestion.
- `src/bot/heartbeat.py`: periodic self-reflection (every `HEARTBEAT_INTERVAL`).
- `src/bot/discord_inbound.py`: optional second transport (Telegram is the required control plane).
- `src/cron/scheduler.py`: lightweight task scheduler; jobs trigger `run_cron_job` in `main.py`, which calls the LLM with recent chat context and DMs the owner.
- `src/hooks/runner.py`: event hooks (`startup`/`message`/`command`/`heartbeat`) auto-discovered from `.workspace/hooks/` then `hooks/`; built-ins log to the audit trail.
- `src/audit_logging/command_logger.py`: append-only audit trail of every action.
- `src/utils/patch_self.py`: backup-then-write self-modification helper (powers `restore_from_backup`).

## Conventions & gotchas

- **Lazy imports are deliberate.** Many modules import inside functions (e.g. LiteLLM, telegram `Bot`, vault helpers) specifically to keep RAM/startup low on the Pi. Don't hoist them to module top-level.
- **Config is centralized** in `src/config.py` — all env vars, paths, presets, and tuning constants (`MAX_TOOL_CALLS`, `HEARTBEAT_INTERVAL`, `MODEL_CONTEXT_TOKENS`, timeouts). Add new config there, not scattered.
- **`.workspace/` is runtime state, not source.** It's gitignored and created from `templates/`. Edit `templates/` to change defaults for fresh installs; the live bot's persona is whatever is in `.workspace/`.
- **Access control defaults to deny.** Empty `ALLOWED_USERS` blocks everyone unless `ALLOW_ALL_USERS=1`. Lite-mode tools are on by default (`ENABLE_LITELLM_TOOLS=1`); set to `0` for a locked-down bot.
- **No sandbox.** The bot runs on bare metal and can run shell, edit files, push git, and call external APIs. The safety guards in `litellm_connector.py` are the only barrier — treat them as security-critical.
- The bot can modify and restart **itself** (`coding` skill, `write_file`, `safe_restart`/`restart_self`, `manage_service`). When editing tool or display code, remember a bad change can be auto-deployed by the running bot.
