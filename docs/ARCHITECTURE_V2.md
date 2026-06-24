# OpenClawGotchi v2 — Architecture Design

> **Status:** Draft / proposal. This is a design doc for a possible ground-up v2,
> parked on a branch for easy reading — **not** intended to merge into this repo.
> Close the PR without merging once you've copied what you need.

**Targets:** Pi Zero 2W-class hardware (~512 MB), remote LLMs, E-Ink body
**Drivers:** (1) RAM & crash robustness, (2) true multi-channel gateway, (3) clean, typed, testable architecture
**Non-goals:** local/on-device LLM, GPU, heavyweight frameworks, on-device compilation

## 1. Design principles

1. **Heavy work is transient, never resident.** The always-on footprint stays tiny; LLM/tool memory lives only for the duration of a turn and is then reclaimed.
2. **One security boundary, in one place.** All privileged side effects flow through a single capability broker with an explicit policy — no safety logic scattered through the agent code.
3. **Channels are adapters, not special cases.** Everything normalizes to one envelope on one bus. Telegram is not the control plane; it's an adapter.
4. **Workers are (mostly) pure.** An agent turn is `job → result + requested side effects`. Side effects are brokered, not performed ad hoc. This is what makes it testable.
5. **Crash isolation by process.** Fragile things (SPI/Pillow, the agent loop) live in supervised child processes. A crash respawns; it never takes the pet down.
6. **Language-neutral seams.** Inter-component contracts are JSON envelopes so any component can later be re-implemented in another language without touching the others.

## 2. High-level architecture

```
            systemd (supervises the core only)
                      |
+---------------------v-------------------------------------------+
|  CORE  (always-on, small -- NEVER imports LLM/tool libs)        |
|                                                                 |
|  adapters/  telegram . discord . signal . webhook  --+          |
|                                                      v          |
|                          +-------- message bus -------+         |
|                          |  normalized Envelope       |         |
|                          +-------------+--------------+         |
|   memory service  <-------------------+  router (build Job)     |
|   (sqlite + vault)                    |                         |
|   capability broker <-----------------+  turn queue (1 slot)    |
|   (policy + execute + audit)          |                         |
|   web ui + plugins                    v                         |
|   watchdog ---------------------> spawn AGENT WORKER            |
+---------------------------------------+-------------------------+
   | render directives                  | Job (stdin)       ^
   v                                    v                   | capability
+- DISPLAY SERVICE -+      +- AGENT WORKER (ephemeral) ------+--------+
| owns SPI/GPIO      |     | loads LLM + tools, runs the loop         |
| renders E-Ink      |     | read-only tools run in-process           |
| snapshots PNG      |     | privileged tools -> broker over socket   |
| crash-isolated     |     | writes Result, EXITS (RAM reclaimed)     |
+--------------------+     +------------------------------------------+
```

Two levels of supervision: **systemd → core**, **core → (adapters, display service, agent worker)**.

## 3. The contracts (the heart of it)

Use **`msgspec`** — tiny, fast, typed structs with JSON encode/decode; ideal on constrained hardware (much lighter than pydantic). Define once in `contracts/` and share across components.

**Envelope** (adapter → bus): one inbound event, channel-normalized.

```jsonc
{
  "id": "uuid",
  "ts": "2026-06-15T21:00:00Z",
  "channel": "telegram",
  "conversation": "telegram:123456",     // stable thread key, used as memory partition
  "sender": { "id": "987", "display": "Elliot", "is_owner": true },
  "kind": "text|voice|image|document|command|webhook|system",
  "text": "what's the weather?",
  "attachments": [ { "type": "image", "uri": "file:///tmp/x.png", "mime": "image/png" } ],
  "meta": {}                              // channel-specific extras
}
```

**Job** (core → worker, on stdin): everything the turn needs, pre-assembled so the worker does zero discovery.

```jsonc
{
  "job_id": "uuid",
  "trigger": { /* Envelope, or {"kind":"heartbeat"} / {"kind":"cron","name":"..."} */ },
  "context": {
    "history": [ { "role": "user", "content": "...", "ts": "..." } ],
    "retrieval": [ { "source": "vault", "text": "..." } ],
    "persona": "...contents of SOUL/IDENTITY...",
    "allowed_tools": ["recall_facts", "read_file", "remember_fact", "show_face"],
    "budget": { "max_tool_calls": 20, "context_tokens": 64000, "wallclock_s": 120 }
  },
  "mode": "lite|pro",
  "broker_socket": "/run/gotchi/broker.sock"
}
```

**Capability request** (worker → broker, mid-loop, for privileged tools only):

```jsonc
{ "job_id": "uuid", "tool": "write_file", "args": { "path": "src/x.py", "content": "..." } }
// broker replies:
{ "ok": true, "result": "wrote 412 bytes" }      // or {"ok": false, "error": "denied: protected path"}
```

**Result** (worker → core, on stdout at end): user-facing reply + declarative side effects the core applies.

```jsonc
{
  "job_id": "uuid",
  "status": "ok|error|rate_limited",
  "reply": "It's 18C and clear.",                  // control tags already stripped
  "directives": [
    { "type": "face", "mood": "happy" },
    { "type": "say", "text": "18C" },
    { "type": "deliver", "conversation": "telegram:123456", "text": "It's 18C and clear." }
  ],
  "memory_writes": [ { "kind": "fact", "category": "weather", "text": "..." } ],
  "usage": { "tokens": 1840, "tool_calls": 2, "ms": 5100 },
  "error": null
}
```

**Why this split matters:** read-only tools (`recall`, `read_file`, web search) run *inside* the worker for speed. Anything with an external side effect (`shell`, `write_file`, `git`, `service control`, sending to another channel) is **brokered** — the worker asks, the core checks the policy, executes, audits, and returns the result so the loop can continue. The agent never holds the keys; the core does. That's the entire safety story, in one component, testable in isolation.

## 4. Components

| Component | Process | Responsibility | Loads LLM libs? |
|---|---|---|---|
| **Core/supervisor** | 1, always-on | bus, router, turn queue, watchdog | No |
| **Channel adapters** | in-core (async tasks) | normalize in/out per channel | No |
| **Capability broker** | in-core | permission policy + execute privileged tools + audit | No |
| **Memory service** | in-core (lib) | sqlite + vault + retrieval; builds Job context | No |
| **Agent worker** | spawned per turn | LLM tool loop; emits Result | Yes (transient) |
| **Display service** | 1, long-lived | owns SPI/GPIO, renders, snapshots PNG | No |
| **Web UI + plugins** | in-core (aiohttp) | screen mirror, plugin pages, webhooks | No |

**Turn queue = 1 slot.** Only one agent worker runs at a time (peak RAM = core + one worker). Channels receive concurrently; agent execution serializes — same idea as today's `router.lock`, but now it also *bounds memory*.

**Display service** is long-lived (not spawned per update like today) so you stop paying Python startup on every face change; it holds GPIO and renders on demand from directives. Watchdog respawns it on crash; plugin `on_ui_render` runs here.

## 5. Request lifecycle

1. Telegram adapter receives a message → builds **Envelope** → publishes to bus.
2. Router pulls it, asks memory service for history+retrieval, consults the permission policy for `allowed_tools`, assembles a **Job**, enqueues it.
3. Turn queue spawns an **agent worker**, writes the Job to its stdin.
4. Worker runs the loop. `recall`/`read` run locally; `write_file`/`shell` go to the **broker** over the unix socket (policy-checked, audited).
5. Worker prints **Result**, exits → its RAM is gone.
6. Core applies `directives` (deliver replies via adapters, send render directives to the display service) and `memory_writes` (memory service). Audit log gets the tool trace.

## 6. RAM reasoning

- **Core resident:** asyncio + adapters + sqlite + aiohttp, no LLM libs → tens of MB, flat.
- **Worker peak:** LiteLLM/tools/context for one turn → transient, serialized, freed on exit. No slow bloat across a long uptime (today's silent killer).
- **Peak = core + one worker**, comfortably inside 512 MB with headroom for the display service.
- **The key tuning knob — cold start vs RAM:** spawning Python per turn costs ~0.3–1 s of imports on a Pi Zero. Options: (a) **pure ephemeral** (best RAM, worst latency), (b) **recycled worker** — keep one warm, recycle it every N turns or when RSS crosses a threshold ("ephemeral-ish," best balance), (c) **prefork pool of 1**. Recommend (b).

## 7. Tech stack

| Layer | Pick | Why |
|---|---|---|
| Core, adapters, broker, web | **Python 3.11+ / asyncio** | one language to start; clean async gateway |
| Contracts | **msgspec** | tiny, typed, fast JSON structs — constrained-friendly |
| Agent worker | **Python** + LiteLLM/openai/anthropic | portable from today's tool loop; self-mod stays viable |
| Telegram | python-telegram-bot (or raw Bot API for less weight) | |
| Display | Python + Pillow + Waveshare driver | don't reinvent; lift from today's repo |
| Memory | SQLite (FTS5) + markdown/Obsidian vault | keep the 3-layer design — it's good |
| IPC | unix domain sockets + line-delimited JSON | language-neutral seam |
| Supervision | systemd (core) + in-core watchdog (children) | |
| Tests | pytest | the thing today's repo lacks |

## 8. Repo layout

```
gotchi/
  contracts/      envelope.py  job.py  result.py        # msgspec structs (the seam)
  core/           supervisor.py  bus.py  router.py  broker.py  watchdog.py  queue.py
  adapters/       telegram.py  discord.py  webhook.py  base.py
  agent/          worker.py  loop.py  prompts.py  tools/
  policy/         permissions.py                         # capability policy (one place)
  memory/         store.py  vault.py  retrieval.py
  display/        service.py  render.py  faces.py
  web/            server.py  plugins.py
  extensions/     skills/ (markdown)   plugins/ (python body)
  workspace/      runtime persona + memory (gitignored)
  tests/
  pyproject.toml
```

## 9. What to lift from v1 (don't rewrite)

- **E-Ink rendering + faces + variant handling** → `display/`. Hard-won; copy it.
- **The tool loop + tool implementations + prompt assembly** → `agent/`. Refactor so privileged tools call the broker instead of acting directly.
- **The 3-layer memory + vault + dreaming/crystallization** → `memory/`.
- **The safety lists** (`DANGEROUS_COMMANDS`, protected files, etc.) → become the `policy/` ruleset, now enforced in the broker.
- **Web UI + plugins + `on_ui_render`** → `web/` + `display/` almost as-is.

## 10. Build order

- **M0 — skeleton (a weekend):** core + telegram adapter + spawn a worker that does one LLM call + show a face. Prove the seam end-to-end.
- **M1 — harden the seam:** msgspec contracts; broker + `policy/` for `shell`/`write_file`; audit in core.
- **M2 — memory:** store + retrieval + persona injected into Job context.
- **M3 — gateway:** second adapter (Discord/Signal) + heartbeat/cron driven by the core.
- **M4 — body:** web UI + plugins + `on_ui_render` via the display service.
- **M5 — parity:** multimodal, self-mod semantics, polish.

## 11. Risks & open questions

- **Worker cold-start latency** — the central tradeoff; settle the recycle policy early (M1).
- **Self-modification across the split** — worker code edits apply on next spawn (easy); core edits need a supervised restart (define the protocol: write → validate → broker triggers core restart).
- **Display service holding GPIO** vs per-spawn isolation — long-lived service is faster but must be rock-solid; keep the watchdog aggressive.
- **Broker chattiness** — many small socket round-trips per turn; batch where possible, keep the socket local.
- **Backpressure** — if turns queue faster than they run, define drop/coalesce rules per conversation.

## 12. The Go upgrade path (later, only if needed)

Because the seam is JSON over sockets, you can replace **`core/` + `adapters/` + the broker/web sockets** with Go (goroutines per channel = tiny RAM for many persistent connections, bulletproof daemon) and **keep `agent/`, `display/`, `memory/` in Python untouched**. The contracts don't change. Do this only if channel count or RAM pressure demands it — don't pay the polyglot tax up front.

---

**One-sentence summary:** a tiny always-on Python core that brokers every privileged action and spawns ephemeral agent workers for the heavy thinking, with JSON seams so you can swap the core to Go later.
