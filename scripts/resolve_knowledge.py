#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge import KnowledgeContext, KnowledgeResolver
from knowledge.errors import KnowledgeResolverError


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve NPC access to a Lore record")
    parser.add_argument("--character", required=True)
    parser.add_argument("--lore", required=True)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--trace", action="store_true", help="Include the decision trace")
    args = parser.parse_args()
    try:
        context = None
        if args.context:
            with args.context.open("r", encoding="utf-8-sig") as stream:
                payload = json.load(stream)
            context = KnowledgeContext(
                active_responsibilities=frozenset(payload.get("active_responsibilities", [])),
                active_assignments=frozenset(payload.get("active_assignments", [])),
                active_projects=frozenset(payload.get("active_projects", [])),
                active_cases=frozenset(payload.get("active_cases", [])),
                active_incidents=frozenset(payload.get("active_incidents", [])),
                authorizations=frozenset(payload.get("authorizations", [])),
                active_roles=frozenset(payload.get("active_roles", [])),
                artist_teams=frozenset(payload.get("artist_teams", [])),
            )
        result = KnowledgeResolver().resolve(args.character, args.lore, context).to_dict()
        if not args.trace:
            result.pop("trace", None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KnowledgeResolverError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
