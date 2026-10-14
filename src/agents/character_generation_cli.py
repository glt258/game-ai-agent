"""Command-line entry point for the production Character Generation V2 path."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from web.errors import WebApplicationError
from web.mappers.character_generation import to_character_generation_response, to_error_response
from web.schemas.characters import CharacterGenerationRequestDTO
from web.services.character_generation_v2_production import (
    build_character_generation_v2_application,
)


def _request_payload(
    *, scenario: str | None, brief: str | None, brief_file: str | None
) -> tuple[CharacterGenerationRequestDTO, str]:
    """Build the CLI request directly at the production application boundary."""

    supplied = sum(value is not None for value in (scenario, brief, brief_file))
    if supplied != 1:
        raise ValueError("exactly one of --scenario, --brief, or --brief-file is required")
    if scenario == "valid":
        return (
            CharacterGenerationRequestDTO(
                brief=(
                    "设计一个新的五星角色。所属组织：临洲大学行为与能力研究中心。"
                    "定位：偏辅助；性格：表面懒散但观察力很强；希望有明显都市生活感。"
                    "不要设计成秘密实验体，不要改变现有世界观重大设定。"
                ),
                hard_constraints=["五星角色", "不得改变现有世界观重大设定"],
                soft_preferences=["偏辅助", "表面懒散但观察力很强", "都市生活感"],
                forbidden_elements=["秘密实验体", "秘密政府机构"],
                request_id="official_valid_001",
            ),
            scenario,
        )
    if scenario == "conflict":
        return (
            CharacterGenerationRequestDTO(
                brief=(
                    "设计一个新的角色：她是秘密政府能力管理局的一名普通辅助成员。"
                    "定位：偏辅助；保持现代都市生活感。"
                ),
                hard_constraints=["偏辅助"],
                soft_preferences=["都市生活感"],
                request_id="official_conflict_001",
            ),
            scenario,
        )
    if brief is None and brief_file is not None:
        try:
            brief = Path(brief_file).read_text(encoding="utf-8")
        except OSError as error:
            raise ValueError(f"could not read --brief-file: {error}") from error
    if brief is None or not brief.strip():
        raise ValueError("custom brief must not be empty")
    return (
        CharacterGenerationRequestDTO(
            brief=brief,
            request_id="official_custom_001",
        ),
        "custom",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a character through the production V2 pipeline."
    )
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--scenario", choices=("valid", "conflict"))
    inputs.add_argument("--brief", help="Character design brief")
    inputs.add_argument("--brief-file", help="UTF-8 file containing the design brief")
    parser.add_argument("--model", choices=("offline", "live"), default="offline")
    parser.add_argument("--provider", help="Live provider override")
    parser.add_argument("--model-name", help="Live model override")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    if args.scenario is None and args.brief is None and args.brief_file is None:
        parser.print_help(sys.stderr)
        return 2

    try:
        payload, scenario = _request_payload(
            scenario=args.scenario,
            brief=args.brief,
            brief_file=args.brief_file,
        )
    except ValueError as error:
        parser.error(str(error))

    environment = dict(os.environ)
    if args.provider:
        environment["NPC_LLM_PROVIDER"] = args.provider
    if args.model_name:
        environment["NPC_LLM_MODEL"] = args.model_name
    try:
        application = build_character_generation_v2_application(
            environment=environment,
            generation_mode=args.model,
        )
        result = application.generate(payload)
        response = to_character_generation_response(payload, result)
    except WebApplicationError as error:
        if args.as_json:
            print(
                json.dumps(
                    {"error": to_error_response(error).model_dump()},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"{error.code}: {error.message}", file=sys.stderr)
        return 2

    if args.as_json:
        output = response.model_dump()
        output["cli"] = {
            "scenario": scenario,
            "model_mode": args.model,
            "route": result.route.value,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print("Character Generation V2")
        print(f"Scenario: {scenario}")
        print(f"Route: {result.route.value}")
        print(f"Name: {result.authoring.final_draft.name}")
        print(f"Canon: {result.authoring.final_check.status.value}")
        print(f"Evaluation: {result.evaluation.outcome.value}")

    failed = (
        result.authoring.final_status.value == "fail"
        or result.evaluation.outcome.value == "FAIL"
    )
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
