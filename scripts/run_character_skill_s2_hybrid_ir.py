"""Run or plan the isolated Hybrid Semantic IR H3 experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from character_intelligence.hybrid_ir import (  # noqa: E402
    HybridGenerationContext,
    HybridSemanticIRRunner,
)


def _context() -> HybridGenerationContext:
    return HybridGenerationContext(
        "Design a support ability that enables an ally after the ability is invoked.",
        allowed_actors=("self", "ally"),
        allowed_trigger_events=("ability_invoked", "feedback_received"),
        allowed_feedback_events=("effect_resolved",),
        allowed_feedback_relations=("enables",),
        allowed_modes=("active",),
        allowed_roles=("support",),
        allowed_centralities=("core",),
    )


def _evaluation_context() -> dict[str, object]:
    return {
        "intent": {
            "mechanic_requirements": [
                {
                    "requirement_id": "req_support",
                    "trigger": {"subject_kinds": ["self"], "events": ["ability_invoked"], "source_kinds": []},
                    "effect": {"subject_kinds": ["ally"], "operations": ["ally_enablement"], "object_kinds": []},
                    "feedback": {"required": True, "events": ["effect_resolved"], "operations": ["enables"]},
                }
            ],
            "forbidden_mechanic_families": [],
            "hard_constraint_conflicts": [],
        },
        "combat_role_profile": {"primary_role": "support", "secondary_roles": []},
        "reference_review_context": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hybrid Semantic IR H3 runner (dry-run by default)")
    parser.add_argument("--live", action="store_true", help="explicitly execute the one frozen H3 provider observation")
    parser.add_argument("--output", type=Path, default=None, help="local ignored evidence path")
    args = parser.parse_args(argv)

    runner = HybridSemanticIRRunner(ROOT, _context())
    if not args.live:
        print(json.dumps(runner.dry_run(), ensure_ascii=False, sort_keys=True))
        return 0
    result = runner.run_live(_evaluation_context(), output_path=args.output)
    payload = {
        "status": result.status,
        "consumed": result.consumed,
        "provider_factory_constructed": result.provider_factory_constructed,
        "provider_called": result.provider_called,
        "transport_attempts": result.transport_attempts,
        "latency_ms": result.latency_ms,
        "provider_outcome": result.provider_outcome,
        "first_failure_layer": result.first_failure_layer,
        "stages": dict(result.stages),
        "evidence_path": str(result.evidence_path) if result.evidence_path is not None else None,
        "run_id": result.evidence.run_id if result.evidence is not None else None,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
