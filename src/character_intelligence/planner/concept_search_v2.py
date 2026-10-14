"""Bounded multi-concept search and selection for the V2 production workflow."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from agents import (
    AgentModel,
    AgentPrompt,
    ConversationMessage,
    ModelInvocationAudit,
    ModelTurn,
    NpcCharacterView,
    NpcRuntimeView,
)

from ..context.schema import CharacterPlanningContextV2
from .character_concept_v2 import (
    CharacterConceptSeedStatus,
    CharacterConceptSeedV2,
    CharacterConceptSelectionV2,
    CharacterConceptV2Error,
    validate_character_concept_search_response,
    validate_character_concept_selection,
    validate_concept_seed_set,
)
from .character_planner_v2 import (
    CharacterPlannerV1Result,
    build_character_planner_prompt,
    run_character_planner_v1,
)

CONCEPT_SEARCH_RESPONSE_FORMAT = "character_concept_search"
CONCEPT_SEARCH_INVOCATION_PURPOSE = "character_concept_search_v2"
CONCEPT_SELECTION_RESPONSE_FORMAT = "character_concept_selection"
CONCEPT_SELECTION_INVOCATION_PURPOSE = "character_concept_selection_v2"

CONCEPT_SEARCH_SYSTEM_CONTRACT = """You are Concept Search v1 in the Character Generation V2 production pipeline.

SYSTEM ROLE
Generate exactly three thin CharacterConceptSeedV2 directions before full planning.

SEARCH RULES
- Do not take the first viable concept and produce stylistic or adjective variations.
- Explore distinct explanations for why this character should exist, what conflict they bring, what relationship space they occupy, what fantasy they offer the player, and what visual idea organizes them.
- Keep all three concepts inside USER HARD REQUIREMENTS, PROJECT CANON, deterministic semantics, roster evidence, and known GAP limits.
- Missing context is uncertainty, never permission to invent roster, combat, story, acceptance, product, or release facts.
- Reference precedent is contrast only, never project truth or a parts catalog.
- Gameplay is one concise fantasy, not a kit, resource model, state machine, or skill loop.
- Relationships are one conceptual axis, not a list of detailed relationship edges.
- Visuals are one high-level anchor, not an image prompt or clothing inventory.

OUTPUT CONTRACT
Return exactly one JSON object with a concepts array containing exactly three seeds. Each seed must use only the requested compact fields. Do not output biography, a full plan, product/release metadata, Canon facts, relationship writes, numeric scores, or prose outside the JSON object.
"""

CONCEPT_SELECTION_SYSTEM_CONTRACT = """You are Concept Selector v1 in the Character Generation V2 production pipeline.

SYSTEM ROLE
Select exactly one existing concept seed for bounded full Planner elaboration.

SELECTION RULES
- Judge hard-requirement fit, Canon safety, evidence-grounded differentiation, relationship potential, narrative utility, gameplay/character linkage, visual identity, and genericness/trope risk.
- Respect known GAPs. Do not invent an unused roster slot, unique combat niche, accepted status, current story fact, or product position.
- Do not choose by 'most unique'. Choose the strongest combination of coherence, differentiation, future narrative value, relationship potential, and compatibility with hard constraints.
- Return only the selected ID and concise decision evidence. Never rewrite a seed or produce a full plan.

OUTPUT CONTRACT
Return exactly one CharacterConceptSelection object with one selected_concept_id, concise selection_reasons, and optional compact tradeoffs, preserve_elements, and rejected_reasons arrays. Do not return seeds, Canon facts, or product/release metadata.
"""


@dataclass(frozen=True)
class ConceptSearchDiagnostics:
    logical_invocation_count: int
    concept_count: int
    distinct_axes: tuple[str, ...]
    structured_parse_succeeded: bool
    model_invocation: ModelInvocationAudit | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_invocation_count": self.logical_invocation_count,
            "concept_count": self.concept_count,
            "distinct_axes": list(self.distinct_axes),
            "structured_parse_succeeded": self.structured_parse_succeeded,
            "model_invocation": (
                self.model_invocation.to_dict()
                if self.model_invocation is not None
                else None
            ),
        }


@dataclass(frozen=True)
class ConceptSearchResult:
    seeds: tuple[CharacterConceptSeedV2, ...]
    diagnostics: ConceptSearchDiagnostics

    def to_dict(self) -> dict[str, Any]:
        return {
            "seeds": [seed.to_dict() for seed in self.seeds],
            "diagnostics": self.diagnostics.to_dict(),
        }


@dataclass(frozen=True)
class ConceptSelectionDiagnostics:
    logical_invocation_count: int
    selected_concept_id: str
    structured_parse_succeeded: bool
    model_invocation: ModelInvocationAudit | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_invocation_count": self.logical_invocation_count,
            "selected_concept_id": self.selected_concept_id,
            "structured_parse_succeeded": self.structured_parse_succeeded,
            "model_invocation": (
                self.model_invocation.to_dict()
                if self.model_invocation is not None
                else None
            ),
        }


@dataclass(frozen=True)
class ConceptSelectionResult:
    seeds: tuple[CharacterConceptSeedV2, ...]
    selection: CharacterConceptSelectionV2
    selected_seed: CharacterConceptSeedV2
    diagnostics: ConceptSelectionDiagnostics

    def to_dict(self) -> dict[str, Any]:
        return {
            "seeds": [seed.to_dict() for seed in self.seeds],
            "selection": self.selection.to_dict(),
            "selected_seed": self.selected_seed.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
        }


@dataclass(frozen=True)
class CharacterPlanningV2Phase4Result:
    search: ConceptSearchResult
    selection: ConceptSelectionResult
    planner: CharacterPlannerV1Result

    @property
    def logical_invocation_count(self) -> int:
        return (
            self.search.diagnostics.logical_invocation_count
            + self.selection.diagnostics.logical_invocation_count
            + self.planner.diagnostics.logical_invocation_count
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "search": self.search.to_dict(),
            "selection": self.selection.to_dict(),
            "planner": self.planner.to_dict(),
            "logical_invocation_count": self.logical_invocation_count,
        }

def _context_payload(context: CharacterPlanningContextV2) -> dict[str, Any]:
    prompt = build_character_planner_prompt(context)
    payload = prompt.authoring_payload
    if not isinstance(payload, Mapping):
        raise CharacterConceptV2Error("Planner context payload is unavailable")
    return deepcopy(dict(payload))


def build_concept_search_prompt(context: CharacterPlanningContextV2) -> AgentPrompt:
    if not isinstance(context, CharacterPlanningContextV2):
        raise TypeError("context must be a CharacterPlanningContextV2")
    planning_context = _context_payload(context)
    payload = {
        "authority_order": planning_context["authority_order"],
        "planning_context": planning_context,
        "seed_fields": [
            "concept_id",
            "one_line_identity",
            "dramatic_axis",
            "character_contradiction",
            "player_hook",
            "relationship_axis",
            "gameplay_fantasy",
            "visual_anchor",
            "differentiation_basis",
            "major_risk",
        ],
        "required_concept_count": 3,
    }
    return _prompt(
        system_contract=CONCEPT_SEARCH_SYSTEM_CONTRACT,
        character_id="concept-search-v2",
        display_name="Character Concept Search v1",
        response_format=CONCEPT_SEARCH_RESPONSE_FORMAT,
        session_id=f"character-concept-search-v2:{context.plan_v2.request_id}",
        invocation_purpose=CONCEPT_SEARCH_INVOCATION_PURPOSE,
        payload=payload,
        message="Produce exactly three meaningfully distinct thin concept seeds.",
    )


def build_concept_selector_prompt(
    context: CharacterPlanningContextV2,
    seeds: Sequence[CharacterConceptSeedV2],
) -> AgentPrompt:
    if not isinstance(context, CharacterPlanningContextV2):
        raise TypeError("context must be a CharacterPlanningContextV2")
    valid_seeds = validate_concept_seed_set(seeds)
    planning_context = _context_payload(context)
    payload = {
        "authority_order": planning_context["authority_order"],
        "planning_context_summary": planning_context,
        "candidate_seeds": [seed.to_provider_dict() for seed in valid_seeds],
        "selection_dimensions": [
            "hard_requirement_fit",
            "canon_safety",
            "evidence_grounded_differentiation",
            "relationship_potential",
            "narrative_utility",
            "gameplay_character_linkage",
            "visual_identity",
            "genericness_or_trope_risk",
        ],
    }
    return _prompt(
        system_contract=CONCEPT_SELECTION_SYSTEM_CONTRACT,
        character_id="concept-selector-v2",
        display_name="Character Concept Selector v1",
        response_format=CONCEPT_SELECTION_RESPONSE_FORMAT,
        session_id=f"character-concept-selector-v2:{context.plan_v2.request_id}",
        invocation_purpose=CONCEPT_SELECTION_INVOCATION_PURPOSE,
        payload=payload,
        message="Select exactly one existing concept seed for Planner elaboration.",
    )


def run_concept_search_v2(
    context: CharacterPlanningContextV2,
    model: AgentModel,
) -> ConceptSearchResult:
    prompt = build_concept_search_prompt(context)
    turn = model.generate(prompt)
    seeds = validate_character_concept_search_response(_structured_output(turn))
    distinct_axes = tuple(
        axis
        for axis in (
            "dramatic_axis",
            "character_contradiction",
            "relationship_axis",
            "gameplay_fantasy",
            "visual_anchor",
        )
        if len({" ".join(getattr(seed, axis).casefold().split()) for seed in seeds}) > 1
    )
    return ConceptSearchResult(
        seeds=seeds,
        diagnostics=ConceptSearchDiagnostics(
            logical_invocation_count=1,
            concept_count=3,
            distinct_axes=distinct_axes,
            structured_parse_succeeded=True,
            model_invocation=turn.invocation,
        ),
    )


def run_concept_selector_v2(
    context: CharacterPlanningContextV2,
    seeds: Sequence[CharacterConceptSeedV2],
    model: AgentModel,
) -> ConceptSelectionResult:
    valid_seeds = validate_concept_seed_set(seeds)
    prompt = build_concept_selector_prompt(context, valid_seeds)
    turn = model.generate(prompt)
    selection = validate_character_concept_selection(
        _structured_output(turn), valid_seeds
    )
    selected_seed = next(
        seed for seed in valid_seeds if seed.concept_id == selection.selected_concept_id
    )
    selected = selected_seed.with_status(CharacterConceptSeedStatus.SELECTED)
    if selected.to_provider_dict() != selected_seed.to_provider_dict():
        raise CharacterConceptV2Error("Selector altered the selected seed")
    return ConceptSelectionResult(
        seeds=valid_seeds,
        selection=selection,
        selected_seed=selected,
        diagnostics=ConceptSelectionDiagnostics(
            logical_invocation_count=1,
            selected_concept_id=selection.selected_concept_id,
            structured_parse_succeeded=True,
            model_invocation=turn.invocation,
        ),
    )


def run_character_planning_v2_phase4(
    context: CharacterPlanningContextV2,
    model: AgentModel,
    *,
    planner_model: AgentModel | None = None,
) -> CharacterPlanningV2Phase4Result:
    """Run one search, one selection, and one existing Planner invocation."""

    if not isinstance(context, CharacterPlanningContextV2):
        raise TypeError("context must be a CharacterPlanningContextV2")
    search = run_concept_search_v2(context, model)
    selection = run_concept_selector_v2(context, search.seeds, model)
    planner = run_character_planner_v1(
        context.plan_v2,
        context,
        planner_model or model,
        selected_concept_seed=selection.selected_seed,
    )
    return CharacterPlanningV2Phase4Result(search, selection, planner)


def _structured_output(turn: ModelTurn) -> object:
    if not isinstance(turn, ModelTurn):
        raise CharacterConceptV2Error("Concept model must return ModelTurn")
    if turn.structured_output is not None:
        return turn.structured_output
    if not isinstance(turn.text, str) or not turn.text.strip():
        raise CharacterConceptV2Error("Concept model returned no structured output")
    try:
        return json.loads(turn.text)
    except json.JSONDecodeError as error:
        raise CharacterConceptV2Error("Concept model returned malformed JSON") from error


def _prompt(
    *,
    system_contract: str,
    character_id: str,
    display_name: str,
    response_format: str,
    session_id: str,
    invocation_purpose: str,
    payload: Mapping[str, Any],
    message: str,
) -> AgentPrompt:
    return AgentPrompt(
        system_contract=system_contract,
        character=NpcCharacterView(
            character_id,
            display_name,
            "planning",
            (),
            (),
            "structured planning",
            "structured planning",
            (),
            "no factual claims",
            "planner",
        ),
        runtime=NpcRuntimeView(
            "planner_v2",
            "Character Generation v2",
            None,
            (),
            (),
        ),
        messages=(ConversationMessage("user", message),),
        available_tools=(),
        session_id=session_id,
        turn_number=1,
        response_format=response_format,
        authoring_payload=payload,
        invocation_purpose=invocation_purpose,
    )


__all__ = [
    "CONCEPT_SEARCH_INVOCATION_PURPOSE",
    "CONCEPT_SEARCH_RESPONSE_FORMAT",
    "CONCEPT_SEARCH_SYSTEM_CONTRACT",
    "CONCEPT_SELECTION_INVOCATION_PURPOSE",
    "CONCEPT_SELECTION_RESPONSE_FORMAT",
    "CONCEPT_SELECTION_SYSTEM_CONTRACT",
    "ConceptSearchDiagnostics",
    "ConceptSearchResult",
    "ConceptSelectionDiagnostics",
    "ConceptSelectionResult",
    "CharacterPlanningV2Phase4Result",
    "build_concept_search_prompt",
    "build_concept_selector_prompt",
    "run_concept_search_v2",
    "run_concept_selector_v2",
    "run_character_planning_v2_phase4",
]
