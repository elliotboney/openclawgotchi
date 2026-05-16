#!/usr/bin/env python3
"""
Lightweight integrity audit for .workspace/knowledge.

Reports:
- missing required frontmatter fields
- status vs status/* tag mismatches
- likely duplicate note titles / stems
- sidecar files (.bak, .ru) that can affect retrieval quality
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / ".workspace" / "knowledge"
NOTES = VAULT / "notes"
REQUIRED_FIELDS = {
    "id",
    "type",
    "note_type",
    "created",
    "source",
    "project",
    "topic",
    "status",
    "tags",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def parse_frontmatter(text: str) -> dict[str, object]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    block = text[4:end]
    data: dict[str, object] = {}
    current_key: str | None = None
    list_mode = False

    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key and list_mode:
            data.setdefault(current_key, [])
            assert isinstance(data[current_key], list)
            data[current_key].append(line[4:].strip().strip('"'))
            continue
        list_mode = False
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if value == "":
            data[key] = []
            list_mode = True
        elif value == "[]":
            data[key] = []
        else:
            data[key] = value.strip('"')
    return data


def normalize_title(text: str) -> str:
    title_match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""
    title = title.lower()
    title = re.sub(r"\s+", " ", title)
    return title


def main() -> int:
    if not NOTES.exists():
        print(f"Vault notes directory not found: {NOTES}")
        return 1

    note_paths = sorted(p for p in NOTES.iterdir() if p.is_file())
    title_map: defaultdict[str, list[Path]] = defaultdict(list)
    stem_map: defaultdict[str, list[Path]] = defaultdict(list)

    missing_field_issues: list[str] = []
    status_issues: list[str] = []
    sidecars: list[str] = []

    for path in note_paths:
        if path.suffix in {".bak", ".ru"} or ".bak." in path.name:
            sidecars.append(str(path.relative_to(ROOT)))

        text = read_text(path)
        meta = parse_frontmatter(text)
        missing = sorted(field for field in REQUIRED_FIELDS if field not in meta)
        if missing:
            missing_field_issues.append(
                f"{path.name}: missing fields -> {', '.join(missing)}"
            )

        status = str(meta.get("status", "")).strip()
        tags = meta.get("tags", [])
        if isinstance(tags, list):
            status_tags = [t for t in tags if str(t).startswith("status/")]
            if status_tags:
                expected = f"status/{status}"
                if expected not in status_tags:
                    status_issues.append(
                        f"{path.name}: status={status!r}, tags={status_tags}"
                    )

        title = normalize_title(text)
        if title:
            title_map[title].append(path)
        stem_map[path.stem.lower()].append(path)

    duplicate_titles = {
        title: paths for title, paths in title_map.items() if len(paths) > 1
    }
    duplicate_stems = {
        stem: paths for stem, paths in stem_map.items() if len(paths) > 1
    }

    print("Vault Audit")
    print(f"- notes scanned: {len(note_paths)}")
    print(f"- missing field issues: {len(missing_field_issues)}")
    print(f"- status/tag issues: {len(status_issues)}")
    print(f"- sidecar files: {len(sidecars)}")
    print(f"- duplicate titles: {len(duplicate_titles)}")
    print(f"- duplicate stems: {len(duplicate_stems)}")

    if missing_field_issues:
        print("\nMissing fields")
        for issue in missing_field_issues[:50]:
            print(f"- {issue}")

    if status_issues:
        print("\nStatus mismatches")
        for issue in status_issues[:50]:
            print(f"- {issue}")

    if sidecars:
        print("\nSidecar files")
        for item in sidecars[:50]:
            print(f"- {item}")

    if duplicate_titles:
        print("\nDuplicate titles")
        for title, paths in list(duplicate_titles.items())[:20]:
            rels = ", ".join(str(p.relative_to(ROOT)) for p in paths)
            print(f"- {title}: {rels}")

    if duplicate_stems:
        print("\nDuplicate stems")
        for stem, paths in list(duplicate_stems.items())[:20]:
            rels = ", ".join(str(p.relative_to(ROOT)) for p in paths)
            print(f"- {stem}: {rels}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
