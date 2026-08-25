from __future__ import annotations

from dataclasses import dataclass

from agents.character_retrieval import (
    CharacterRetrievalPlan,
    build_character_retrieval_plan,
)


@dataclass(frozen=True)
class FakeRequest:
    brief: str
    hard_constraints: tuple[str, ...] = ()
    soft_preferences: tuple[str, ...] = ()
    forbidden_elements: tuple[str, ...] = ()
    desired_connections: tuple[str, ...] = ()


def _calls(plan: CharacterRetrievalPlan) -> list[tuple[str, dict[str, object]]]:
    return [(call.name, dict(call.arguments)) for call in plan.tool_calls]


def test_direct_ids_cover_all_types_in_fixed_order_after_world_rules() -> None:
    request = FakeRequest(
        "关联 story_alpha、char_alpha、lore_alpha 和 faction_alpha，也提到 case_alpha。"
    )

    plan = build_character_retrieval_plan(
        request,
        known_source_ids={
            "story_alpha",
            "char_alpha",
            "lore_alpha",
            "faction_alpha",
            "case_alpha",
        },
        known_source_aliases={},
        source_types={
            "story_alpha": "story",
            "char_alpha": "character",
            "lore_alpha": "lore",
            "faction_alpha": "faction",
            "case_alpha": "case",
        },
    )

    assert _calls(plan) == [
        ("get_world_rules", {}),
        ("get_faction", {"faction_id": "faction_alpha"}),
        ("get_lore", {"lore_id": "lore_alpha"}),
        ("get_character", {"character_id": "char_alpha"}),
        ("get_story_context", {"context_id": "case_alpha"}),
        ("get_story_context", {"context_id": "story_alpha"}),
    ]
    assert plan.requires_model_planning is False


def test_unknown_ids_are_not_retrieved() -> None:
    request = FakeRequest("参考 faction_known、lore_unknown、char_unknown 和 incident_unknown。")

    plan = build_character_retrieval_plan(
        request,
        known_source_ids={"faction_known"},
        known_source_aliases={},
        source_types={"faction_known": "faction"},
    )

    assert _calls(plan) == [
        ("get_world_rules", {}),
        ("get_faction", {"faction_id": "faction_known"}),
    ]
    assert "lore_unknown" not in repr(plan.tool_calls)
    assert "char_unknown" not in repr(plan.tool_calls)
    assert "incident_unknown" not in repr(plan.tool_calls)


def test_aliases_use_chinese_substrings_and_ascii_token_boundaries() -> None:
    request = FakeRequest("加入临洲大学研究中心，参考 AIG 的资料，也参考 Project X。")

    plan = build_character_retrieval_plan(
        request,
        known_source_ids={"faction_001", "lore_001", "lore_002"},
        known_source_aliases={
            "faction_001": ("临洲大学",),
            "lore_001": ("AI",),
            "lore_002": ("Project X",),
        },
        source_types={
            "faction_001": "faction",
            "lore_001": "lore",
            "lore_002": "lore",
        },
    )

    assert _calls(plan) == [
        ("get_world_rules", {}),
        ("get_faction", {"faction_id": "faction_001"}),
        ("get_lore", {"lore_id": "lore_002"}),
    ]


def test_clear_category_intents_add_all_four_searches_in_fixed_order() -> None:
    request = FakeRequest("查询现有阵营、世界观设定、既有角色和相关事件。")
    query = "查询现有阵营、世界观设定、既有角色和相关事件。"

    plan = build_character_retrieval_plan(
        request,
        known_source_ids=set(),
        known_source_aliases={},
        source_types={},
    )

    assert _calls(plan) == [
        ("get_world_rules", {}),
        ("search_factions", {"query": query, "limit": 5}),
        ("search_lore", {"query": query, "limit": 5}),
        ("search_characters", {"query": query, "limit": 5}),
        ("search_story_context", {"query": query, "limit": 5}),
    ]
    assert plan.requires_model_planning is False


def test_all_request_fields_participate_in_query() -> None:
    request = FakeRequest(
        "brief-marker",
        hard_constraints=("hard-marker",),
        soft_preferences=("soft-marker",),
        forbidden_elements=("forbidden-marker",),
        desired_connections=("lore connection",),
    )

    plan = build_character_retrieval_plan(
        request,
        known_source_ids=set(),
        known_source_aliases={},
        source_types={},
    )

    search_calls = [call for call in plan.tool_calls if call.name.startswith("search_")]
    assert len(search_calls) == 1
    query = search_calls[0].arguments["query"]
    assert all(marker in query for marker in (
        "brief-marker",
        "hard-marker",
        "soft-marker",
        "forbidden-marker",
        "lore connection",
    ))


def test_semantic_deduplication_and_output_are_stable() -> None:
    request = FakeRequest(
        "faction_001 faction_001 现有阵营 现有阵营",
        desired_connections=("现有阵营",),
    )
    kwargs = {
        "known_source_ids": {"faction_001"},
        "known_source_aliases": {"faction_001": ("阵营",)},
        "source_types": {"faction_001": "faction"},
    }

    first = build_character_retrieval_plan(request, **kwargs)
    second = build_character_retrieval_plan(request, **kwargs)

    assert first == second
    assert [call.name for call in first.tool_calls] == [
        "get_world_rules",
        "get_faction",
    ]
    assert len({call.id for call in first.tool_calls}) == len(first.tool_calls)


def test_explicitly_original_request_does_not_trigger_fallback() -> None:
    plan = build_character_retrieval_plan(
        FakeRequest("设计一个完全原创、不依赖现有 Canon 的角色。"),
        known_source_ids=set(),
        known_source_aliases={},
        source_types={},
    )

    assert _calls(plan) == [("get_world_rules", {})]
    assert plan.requires_model_planning is False


def test_ambiguous_existing_dependency_requests_model_planning() -> None:
    plan = build_character_retrieval_plan(
        FakeRequest("请考虑 existing canon，但没有具体对象或类别。"),
        known_source_ids=set(),
        known_source_aliases={},
        source_types={},
    )

    assert _calls(plan) == [("get_world_rules", {})]
    assert plan.requires_model_planning is True
