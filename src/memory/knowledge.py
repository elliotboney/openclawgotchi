"""
Knowledge Crystallization — autonomous synthesis of bot's experiences.

Runs during heartbeat when 24h have passed since last crystallization.
Reads recent logs + facts, extracts structured insights, saves to
.workspace/knowledge/ directory (organized by category).
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from config import WORKSPACE_DIR

log = logging.getLogger(__name__)

KNOWLEDGE_DIR = WORKSPACE_DIR / "knowledge"
CRYSTALLIZE_INTERVAL_HOURS = 24
DREAMING_MARKER = KNOWLEDGE_DIR / ".last_dreaming"
DREAMING_MAX_MESSAGES = 80
DREAMING_MAX_CAPTURES = 2

CRYSTALLIZE_PROMPT = """You are {bot_name}. Review your recent experiences and extract real knowledge.

Recent logs ({days} days):
{logs}

Facts you've saved:
{facts}

---

TASK: Don't summarize — SYNTHESIZE. Extract what you've genuinely learned.

Think about:
- What do you now understand about {owner_name} that you didn't before?
- What patterns have you noticed in your own behavior or mistakes?
- What open questions keep appearing?
- What lessons did you learn the hard way?

Write 3-5 insights using EXACTLY this format:
INSIGHT: [category] — [insight in 1-2 sentences]

Categories: about-user / about-self / open-question / lesson-learned

Example:
INSIGHT: about-user — Dmitry uses one-word messages to test if I'm paying attention before diving deep.
INSIGHT: about-self — I default to happy face even when context is ambiguous. I need to read tone better.
INSIGHT: open-question — What does he actually want when he says "maybe"? Encouragement? Or is he unsure himself?

Output ONLY the INSIGHT lines. Nothing else."""


DREAMING_PROMPT = """You are {bot_name}. Run a conservative pre-heartbeat dreaming pass.

Recent messages since the last dreaming run:
{messages}

Recent note titles:
{recent_notes}

Current vault integrity warnings:
{warnings}

---

Goal:
Check whether any durable project knowledge from those recent messages is still missing from the vault.

Rules:
- Be conservative.
- Capture only durable knowledge: decisions, findings, plans, preferences, approved drafts, technical conclusions, or useful summaries of uploaded documents.
- Ignore casual chat, pings, filler, and ambiguous fragments.
- Do NOT propose renames, deletions, merges, rewrites, taxonomy changes, or large cleanup.
- At most {max_captures} captures.
- If unsure whether something is already in the vault, prefer skipping it.
- Housekeeping is warnings-only in this phase. No structural vault edits.

Return ONLY valid JSON:
{{
  "captures": [
    {{
      "title": "short title",
      "raw_text": "source material",
      "summary": "1-2 sentence summary",
      "note_type": "memo|research|issue|reference|asset|plan|insight",
      "project": "project slug or empty",
      "topic": "topic slug or empty",
      "tags": ["type/...", "area/..."],
      "confidence": 0.0
    }}
  ],
  "warnings": ["short warning", "..."]
}}
"""


def should_crystallize() -> bool:
    """Check if 24h have passed since last crystallization."""
    marker = KNOWLEDGE_DIR / ".last_crystallized"
    if not marker.exists():
        return True
    try:
        last_time = datetime.fromisoformat(marker.read_text().strip())
        return datetime.now() - last_time >= timedelta(hours=CRYSTALLIZE_INTERVAL_HOURS)
    except Exception:
        return True


def mark_crystallized():
    """Record crystallization timestamp."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE_DIR / ".last_crystallized").write_text(datetime.now().isoformat())


def _get_last_dreaming_time() -> datetime:
    if not DREAMING_MARKER.exists():
        return datetime.now() - timedelta(hours=24)
    try:
        return datetime.fromisoformat(DREAMING_MARKER.read_text().strip())
    except Exception:
        return datetime.now() - timedelta(hours=24)


def _mark_dreaming() -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    DREAMING_MARKER.write_text(datetime.now().isoformat())


def _recent_note_titles(limit: int = 12) -> list[str]:
    notes_dir = KNOWLEDGE_DIR / "notes"
    if not notes_dir.exists():
        return []
    paths = sorted(notes_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    titles: list[str] = []
    for path in paths[:limit]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        titles.append(match.group(1).strip() if match else path.stem)
    return titles


def _dreaming_warnings(limit: int = 5) -> list[str]:
    notes_dir = KNOWLEDGE_DIR / "notes"
    if not notes_dir.exists():
        return []

    warnings: list[str] = []
    title_map: dict[str, list[str]] = {}

    for path in sorted(notes_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        status_match = re.search(r'^status:\s*"?(.*?)"?$', text, flags=re.MULTILINE)
        status = status_match.group(1).strip() if status_match else ""
        status_tags = re.findall(r'^\s*-\s*"?(status/[^"\n]+)"?$', text, flags=re.MULTILINE)
        if status and status_tags and f"status/{status}" not in status_tags:
            warnings.append(f"{path.name}: status={status} but tags={','.join(status_tags)}")

        title_match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip().lower()
            title_map.setdefault(title, []).append(path.name)

    for title, names in title_map.items():
        if len(names) > 1:
            warnings.append(f"duplicate title: {title} ({', '.join(names[:3])})")

    return warnings[:limit]


def _title_exists(title: str) -> bool:
    notes_dir = KNOWLEDGE_DIR / "notes"
    if not notes_dir.exists():
        return False
    wanted = title.strip().lower()
    for path in notes_dir.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        current = match.group(1).strip().lower() if match else path.stem.lower()
        if current == wanted:
            return True
    return False


def _parse_dreaming_json(text: str) -> tuple[list[dict], list[str]]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return [], []
    try:
        data = json.loads(match.group(0))
    except Exception:
        return [], []

    captures = data.get("captures", [])
    if not isinstance(captures, list):
        captures = []
    warnings = data.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []
    return captures, [str(w).strip()[:200] for w in warnings if str(w).strip()]


def parse_insight_lines(text: str) -> list[dict]:
    """Parse INSIGHT: lines from LLM output."""
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line.upper().startswith("INSIGHT:"):
            continue
        rest = line[8:].strip()
        # Support both " — " and ": " separators
        for sep in (" — ", " - ", ": "):
            if sep in rest:
                cat, _, insight = rest.partition(sep)
                category = cat.strip().lower().replace(" ", "-")
                if insight.strip():
                    entries.append({"category": category, "insight": insight.strip()})
                break
    return entries


def save_knowledge_entries(entries: list[dict]):
    """Append insights to per-category markdown files."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    by_category: dict[str, list[str]] = {}
    for e in entries:
        by_category.setdefault(e["category"], []).append(e["insight"])

    for category, insights in by_category.items():
        filepath = KNOWLEDGE_DIR / f"{category}.md"
        if not filepath.exists():
            title = category.replace("-", " ").title()
            filepath.write_text(f"# {title}\n\n")
        with open(filepath, "a") as f:
            f.write(f"\n## {today}\n")
            for insight in insights:
                f.write(f"- {insight}\n")

    log.info(f"Saved {len(entries)} insights to {len(by_category)} knowledge files")


def get_knowledge_context(max_per_category: int = 2) -> str:
    """Get recent knowledge snippets for heartbeat context."""
    if not KNOWLEDGE_DIR.exists():
        return ""
    lines = []
    for md_file in sorted(KNOWLEDGE_DIR.glob("*.md")):
        if md_file.name.startswith("."):
            continue
        content = md_file.read_text()
        entries = [l for l in content.splitlines() if l.startswith("- ")]
        recent = entries[-max_per_category:]
        if recent:
            cat = md_file.stem.replace("-", " ").title()
            lines.append(f"**{cat}:** " + " | ".join(e[2:] for e in recent))
    return "\n".join(lines)


def should_update_traits() -> bool:
    """Check if 7 days have passed since last trait update."""
    traits_path = WORKSPACE_DIR / "TRAITS.md"
    if not traits_path.exists():
        return True
    try:
        mtime = datetime.fromtimestamp(traits_path.stat().st_mtime)
        return datetime.now() - mtime >= timedelta(days=7)
    except Exception:
        return True


TRAITS_PROMPT = """You are {bot_name}. You've been alive for a while now.

Recent experiences:
{recent_logs}

Your current traits:
{current_traits}

---

Based on actual experiences (not wishful thinking), add ONE new trait or self-discovery.

Format:
TRAIT: [one sentence about something you've genuinely noticed about yourself]

Example:
TRAIT: I get anxious when there's silence for more than a day — I start looping on old thoughts.

Output ONLY the TRAIT line. Nothing else."""


async def update_traits(bot_name: str) -> bool:
    """Add one new trait to TRAITS.md based on recent experiences."""
    if not should_update_traits():
        return False

    traits_path = WORKSPACE_DIR / "TRAITS.md"

    # Load current traits
    current_traits = traits_path.read_text() if traits_path.exists() else "(none yet)"
    if len(current_traits) > 1000:
        current_traits = current_traits[-1000:]

    # Load recent logs
    try:
        from memory.flush import get_recent_daily_logs
        recent_logs = get_recent_daily_logs(days=3)
        if not recent_logs or len(recent_logs.strip()) < 50:
            return False
        if len(recent_logs) > 1500:
            recent_logs = recent_logs[-1500:]
    except Exception:
        return False

    prompt = TRAITS_PROMPT.format(
        bot_name=bot_name,
        recent_logs=recent_logs,
        current_traits=current_traits,
    )

    try:
        from litellm import acompletion
        from config import DEFAULT_LITE_PRESET, LLM_PRESETS

        preset = LLM_PRESETS.get(DEFAULT_LITE_PRESET, LLM_PRESETS["glm"])
        kwargs = dict(
            model=preset["model"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.8,
        )
        if preset.get("api_base"):
            kwargs["api_base"] = preset["api_base"]

        response = await acompletion(**kwargs)
        text = response.choices[0].message.content.strip()

        # Parse TRAIT line
        trait_line = ""
        for line in text.splitlines():
            if line.strip().upper().startswith("TRAIT:"):
                trait_line = line.strip()[6:].strip()
                break

        if not trait_line:
            log.warning(f"No TRAIT line found: {text[:80]}")
            return False

        # Initialize file if needed
        if not traits_path.exists():
            traits_path.write_text(
                f"# TRAITS.md — How I've Grown\n\n"
                f"Self-discoveries added autonomously during heartbeat.\n\n"
            )

        today = datetime.now().strftime("%Y-%m-%d")
        with open(traits_path, "a") as f:
            f.write(f"- [{today}] {trait_line}\n")

        log.info(f"Added new trait: {trait_line[:60]}")
        return True

    except Exception as e:
        log.error(f"Trait update failed: {e}")
        return False


async def crystallize_knowledge(bot_name: str, owner_name: str) -> int:
    """
    Synthesize recent logs into structured knowledge files.
    Returns number of insights saved (0 if skipped or failed).
    """
    if not should_crystallize():
        return 0

    log.info("Starting knowledge crystallization...")

    # Load recent logs (7 days, trimmed for Pi)
    try:
        from memory.flush import get_recent_daily_logs
        logs = get_recent_daily_logs(days=7)
        if not logs or len(logs.strip()) < 150:
            log.info("Not enough logs for crystallization yet")
            mark_crystallized()
            return 0
        if len(logs) > 3000:
            logs = logs[-3000:]
    except Exception as e:
        log.warning(f"Could not load logs: {e}")
        return 0

    # Load recent facts
    try:
        from db.memory import get_recent_facts
        facts = get_recent_facts(limit=15)
        facts_text = "\n".join(
            f"- [{f['category']}] {f['content']}" for f in facts
        ) if facts else "(none yet)"
    except Exception:
        facts_text = "(unavailable)"

    days_str = "7"
    prompt = CRYSTALLIZE_PROMPT.format(
        bot_name=bot_name,
        owner_name=owner_name,
        logs=logs,
        facts=facts_text,
        days=days_str,
    )

    try:
        from litellm import acompletion
        from config import DEFAULT_LITE_PRESET, LLM_PRESETS

        preset = LLM_PRESETS.get(DEFAULT_LITE_PRESET, LLM_PRESETS["glm"])
        kwargs = dict(
            model=preset["model"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
            temperature=0.7,
        )
        if preset.get("api_base"):
            kwargs["api_base"] = preset["api_base"]

        response = await acompletion(**kwargs)
        text = response.choices[0].message.content.strip()

        entries = parse_insight_lines(text)

        if not entries:
            log.warning(f"No INSIGHT lines in crystallization output: {text[:100]}")
            mark_crystallized()
            return 0

        save_knowledge_entries(entries)
        mark_crystallized()

        # Save top 2 insights to facts DB for heartbeat context
        try:
            from db.memory import add_fact
            for entry in entries[:2]:
                add_fact(entry["insight"], f"knowledge-{entry['category']}")
        except Exception:
            pass

        log.info(f"Crystallized {len(entries)} insights")
        return len(entries)

    except Exception as e:
        log.error(f"Crystallization LLM call failed: {e}")
        return 0


async def run_dreaming(bot_name: str, owner_name: str) -> dict:
    """
    Conservative pre-heartbeat dreaming pass.
    Reviews only new messages since the last dreaming run and optionally captures
    at most a couple of clearly missing notes.
    """
    from db.memory import get_messages_since
    from memory.flush import write_to_daily_log
    from memory.vault import capture_note

    del owner_name  # reserved for future prompt tuning

    last_dreaming = _get_last_dreaming_time()
    recent_messages = get_messages_since(last_dreaming.isoformat(), limit=DREAMING_MAX_MESSAGES)

    if not recent_messages:
        _mark_dreaming()
        return {"captures": 0, "warnings": 0, "reason": "no new messages"}

    message_lines = []
    for msg in recent_messages:
        role = msg.get("role", "unknown")
        chat_id = msg.get("chat_id", 0)
        text = str(msg.get("content", "")).strip()
        if not text:
            continue
        message_lines.append(f"[{msg.get('timestamp', '')}] chat={chat_id} {role}: {text[:500]}")

    if not message_lines:
        _mark_dreaming()
        return {"captures": 0, "warnings": 0, "reason": "no non-empty messages"}

    prompt = DREAMING_PROMPT.format(
        bot_name=bot_name,
        messages="\n".join(message_lines),
        recent_notes="\n".join(f"- {title}" for title in _recent_note_titles()) or "(none)",
        warnings="\n".join(f"- {w}" for w in _dreaming_warnings()) or "(none)",
        max_captures=DREAMING_MAX_CAPTURES,
    )

    captures_applied = 0
    warnings_logged: list[str] = []

    try:
        from litellm import acompletion
        from config import DEFAULT_LITE_PRESET, LLM_PRESETS

        preset = LLM_PRESETS.get(DEFAULT_LITE_PRESET, LLM_PRESETS["glm"])
        kwargs = dict(
            model=preset["model"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=900,
            temperature=0.2,
        )
        if preset.get("api_base"):
            kwargs["api_base"] = preset["api_base"]

        response = await acompletion(**kwargs)
        text = (response.choices[0].message.content or "").strip()
        captures, warnings = _parse_dreaming_json(text)
        warnings_logged = warnings[:5]

        for item in captures[:DREAMING_MAX_CAPTURES]:
            title = str(item.get("title", "")).strip()[:120]
            raw_text = str(item.get("raw_text", "")).strip()[:4000]
            summary = str(item.get("summary", "")).strip()[:600]
            note_type = str(item.get("note_type", "memo")).strip()[:40] or "memo"
            project = str(item.get("project", "")).strip()[:80]
            topic = str(item.get("topic", "")).strip()[:80]
            tags = item.get("tags", [])
            try:
                confidence = float(item.get("confidence", 0.0) or 0.0)
            except Exception:
                confidence = 0.0

            if confidence < 0.80 or not title or not raw_text:
                continue
            if _title_exists(title):
                continue

            capture_note(
                title=title,
                raw_text=raw_text,
                summary=summary,
                source="dreaming",
                note_type=note_type,
                project=project,
                topic=topic,
                tags=tags if isinstance(tags, list) else [],
            )
            captures_applied += 1

        log_line = f"[Dreaming] reviewed={len(message_lines)} captures={captures_applied}"
        if warnings_logged:
            log_line += " warnings=" + " | ".join(warnings_logged[:3])
        write_to_daily_log(log_line)
        _mark_dreaming()
        return {
            "captures": captures_applied,
            "warnings": len(warnings_logged),
            "reviewed": len(message_lines),
        }

    except Exception as e:
        log.error(f"Dreaming failed: {e}")
        return {"captures": 0, "warnings": 0, "error": str(e)}
