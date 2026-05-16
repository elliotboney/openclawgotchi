#!/usr/bin/env python3
"""
Debug retrieval against .workspace/knowledge using query token scoring.

This is a read-only helper to test whether real user phrasing would surface
the notes we expect.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from memory.vault import retrieve_vault_context  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="Natural-language query to test against the vault")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of results")
    args = parser.parse_args()

    result = retrieve_vault_context(args.query, limit=args.limit)
    if not result:
        print("No retrieval hits")
        return 0

    print(f"Query: {args.query}")
    print()
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
