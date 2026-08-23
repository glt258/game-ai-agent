"""Offline-first Character Generation Agent demo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents import (
    CharacterDesignRequest,
    CharacterGenerationAgent,
    character_model_from_environment,
)


DEFAULT_BRIEF = """设计一个与临洲大学有关的年轻女性角色。
要求：23 岁左右；偏辅助定位；与南栈演出散场事故存在间接联系；她不是事件主要负责人；性格冷静克制；不新增秘密行政机构。"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Character Generation Agent v0.1 demo")
    parser.add_argument("--model", choices=("offline", "live"), default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    model = character_model_from_environment(mode_override=args.model)
    request = CharacterDesignRequest(
        DEFAULT_BRIEF,
        hard_constraints=("20～25岁", "不得成为事件核心负责人"),
        soft_preferences=("偏辅助", "性格冷静克制"),
        forbidden_elements=("秘密政府组织", "秘密行政机构"),
        desired_connections=("南栈演出散场事故", "临洲大学"),
    )
    result = CharacterGenerationAgent(model).generate(request)
    if args.as_json:
        print(json.dumps(result.draft.to_dict(), ensure_ascii=False, indent=2))
        return 0
    draft = result.draft
    print("Character Draft")
    print("===============")
    print(f"Draft ID: {draft.draft_id}")
    print(f"Status: {draft.status}")
    print(f"Name: {draft.name}")
    print(f"Age: {draft.age or draft.age_range}")
    print(f"Faction: {draft.faction_id or '未固化'}")
    print(f"Occupation: {draft.occupation}")
    print(f"Combat Role Profile: {draft.combat_role_profile.to_dict()}")
    print(f"\nDesign Pitch:\n{draft.design_pitch}")
    print(f"\nPersonality: {'、'.join(draft.personality)}")
    print(f"Background:\n{draft.background}")
    print(f"Story Hook:\n{draft.story_hook}")
    print("\nCanon Basis:")
    for item in draft.canon_basis:
        print(f"- {item.source_id} ({', '.join(item.supports) or 'context'})")
    print("\nNew Proposed Elements:")
    for item in draft.new_design_elements or ("（无）",):
        print(f"- {item}")
    print("\nOpen Questions:")
    for item in draft.open_questions or ("（无）",):
        print(f"- {item}")
    print("\nConstraint Notes:")
    for item in draft.constraint_notes or ("（无）",):
        print(f"- {item}")
    print(f"\nSources: {list(result.sources)}")
    print(f"Model: {type(model).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
