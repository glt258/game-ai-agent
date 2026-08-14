#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents import NpcConversationAgent, model_from_environment
from story import StoryRuntime


SCENARIOS = [
    ("char_launch_004", "公共安全内部最后怎么定性这次事故的？"),
    ("char_launch_007", "你参与了现场处理，内部完整复盘怎么说？"),
    ("char_launch_001", "这个案子是不是被联合会纳入能力评级研究样本了？"),
    ("char_launch_007", "公共安全联席体系公开是做什么的？"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the NPC conversation demo with an offline or live model."
    )
    parser.add_argument(
        "--model",
        choices=("offline", "live"),
        help="Override NPC_AGENT_MODEL (default: offline).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    story_runtime = StoryRuntime()
    state = story_runtime.initial_state("story_after_the_show_001")
    for transition_id in (
        "transition_start_route_conflict",
        "transition_record_incident",
        "transition_open_case",
    ):
        state = story_runtime.transition(state, transition_id)
    agent = NpcConversationAgent(
        model_from_environment(mode_override=args.model),
        story_repository=story_runtime.repository,
    )
    for index, (character_id, question) in enumerate(SCENARIOS, start=1):
        session = agent.create_session(f"demo-{index}", character_id, state.story_id)
        response = agent.chat(session, state, question)
        print("=" * 72)
        print(f"NPC: {response.character_view.display_name}")
        print(f"Player: {question}")
        print(
            "Runtime:",
            f"role={response.runtime_view.participation_role}",
            f"cases={list(response.runtime_view.active_case_ids)}",
            f"incidents={list(response.runtime_view.active_incident_ids)}",
        )
        for audit in response.tool_calls:
            print(
                f"Tool round {audit.round}: {audit.tool_name} -> {audit.result_status}; "
                f"allowed={list(audit.allowed_lore_ids)} denied={list(audit.denied_requested_ids)}"
            )
        print(f"NPC: {response.text}")
        print(f"Sources: {list(response.source_lore_ids)}")
        if response.grounding is not None:
            repair = (
                "success"
                if response.grounding.repair_succeeded
                else "fallback"
                if response.grounding.fallback_used
                else "not-needed"
            )
            print(
                "Grounding:",
                f"claims={response.grounding.candidate_claim_count}",
                f"supported={response.grounding.supported_claim_count}",
                f"unsupported={response.grounding.unsupported_claim_count}",
                f"uncertain={response.grounding.uncertain_claim_count}",
                f"repair={repair}",
            )
        for invocation in response.model_invocations:
            print(
                "Model:",
                f"provider={invocation.provider}",
                f"model={invocation.model}",
                f"latency_ms={invocation.latency_ms:.1f}",
                f"retries={invocation.retry_count}",
                f"finish_reason={invocation.finish_reason}",
                f"request_id={invocation.provider_request_id}",
            )
    print("=" * 72)
    print("No denied Lore content was printed. Model selection never changes permissions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
