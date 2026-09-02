"""Deterministic alignment checks between design intent and a draft."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ..context import EvaluationContext
from ..models import EvaluationFinding

_ROLE_ROWS = {
    "main_dps": {
        "operation": "direct_output",
        "subjects": {"enemy"},
        "triggers": {("self", "ability_invoked")},
    },
    "sub_dps": {
        "operation": "follow_up_output",
        "subjects": {"enemy"},
        "triggers": {("ally", "action_completed"), ("team", "action_completed")},
    },
    "support": {
        "operation": "ally_enablement",
        "subjects": {"ally", "team"},
        "triggers": {
            ("self", "ability_invoked"),
            ("ally", "action_completed"),
            ("team", "action_completed"),
        },
    },
    "healer": {
        "operation": "recover_or_mitigate",
        "subjects": {"ally", "team"},
        "triggers": {
            ("self", "ability_invoked"),
            ("ally", "damage_received"),
            ("team", "damage_received"),
        },
    },
    "control": {
        "operation": "enemy_action_control",
        "subjects": {"enemy"},
        "triggers": {
            ("self", "ability_invoked"),
            ("ally", "action_completed"),
            ("summon", "summon_acted"),
            ("scene", "scene_entered"),
        },
    },
    "defense": {
        "operation": "threat_protection",
        "subjects": {"ally", "team"},
        "triggers": {
            ("self", "ability_invoked"),
            ("ally", "damage_received"),
            ("team", "damage_received"),
        },
    },
}


class RequestAlignmentValidator:
    """Check explicitly requested role signals against generated values."""

    validator_id = "request_alignment"
    dimension = "request_alignment"

    def validate(self, context: EvaluationContext) -> Iterable[EvaluationFinding]:
        if not isinstance(context, EvaluationContext):
            raise TypeError("context must be an EvaluationContext")
        if context.draft is None:
            return ()

        draft = context.draft
        intent = context.intent
        findings: list[EvaluationFinding] = []
        skill_context = context.skill_validation_context
        candidate = context.skill_candidate

        if intent is None:
            self._append_skill_findings(findings, skill_context, candidate)
            return findings

        requested = context.intent_role_profile
        generated = context.draft_role_profile
        assert requested is not None and generated is not None

        if context.expected_affiliation_id is not None and draft.faction_id != context.expected_affiliation_id:
            findings.append(
                EvaluationFinding(
                    validator_id=self.validator_id,
                    code="AFFILIATION_CONSTRAINT_UNSATISFIED",
                    severity="ERROR",
                    blocking=True,
                    stage="request_alignment",
                    field_path="faction_id",
                    message="Generated draft does not satisfy the requested affiliation.",
                )
            )

        if requested.primary_role is not None and generated.primary_role != requested.primary_role:
            findings.append(
                EvaluationFinding(
                    validator_id=self.validator_id,
                    code="REQUEST_PRIMARY_ROLE_MISMATCH",
                    severity="ERROR",
                    blocking=True,
                    stage="request_alignment",
                    field_path="combat_role_profile.primary_role",
                    message=(
                        f"Requested primary role {requested.primary_role!r} does not match "
                        f"generated primary role {generated.primary_role!r}."
                    ),
                )
            )

        missing_secondary = tuple(
            role for role in requested.secondary_roles if role not in generated.secondary_roles
        )
        if missing_secondary:
            findings.append(
                EvaluationFinding(
                    validator_id=self.validator_id,
                    code="REQUEST_SECONDARY_ROLE_MISSING",
                    severity="ERROR",
                    blocking=True,
                    stage="request_alignment",
                    field_path="combat_role_profile.secondary_roles",
                    message=(
                        "Generated draft is missing requested secondary role(s): "
                        f"{', '.join(missing_secondary)}."
                    ),
                )
            )

        self._append_skill_findings(findings, skill_context, candidate)

        return findings

    def _append_skill_findings(self, findings, skill_context, candidate) -> None:
        if skill_context is None or candidate is None:
            return
        if skill_context.intent.hard_constraint_conflicts:
            findings.append(
                EvaluationFinding(
                    validator_id=self.validator_id,
                    code="HARD_CONSTRAINT_CONFLICT",
                    severity="ERROR",
                    blocking=True,
                    stage="request_alignment",
                    field_path="/context/intent/hard_constraint_conflicts",
                    message="SkillKit request contains a hard constraint conflict.",
                )
            )
        families = set()
        if candidate.resources or any(
            effect.operation is not None and effect.operation.startswith("resource_")
            for entry in candidate.entries
            for protocol in entry.protocols
            for effect in protocol.causes
        ):
            families.add("resource")
        if candidate.states or any(
            effect.operation is not None and effect.operation.startswith("state_")
            for entry in candidate.entries
            for protocol in entry.protocols
            for effect in protocol.causes
        ):
            families.add("state")
        if candidate.summons or any(
            effect.operation is not None and effect.operation.startswith("summon_")
            for entry in candidate.entries
            for protocol in entry.protocols
            for effect in protocol.causes
        ):
            families.add("summon")
        for family in sorted(
            set(skill_context.intent.forbidden_mechanic_families) & families
        ):
            findings.append(
                EvaluationFinding(
                    validator_id=self.validator_id,
                    code=f"FORBIDDEN_{family.upper()}_INTRODUCED",
                    severity="ERROR",
                    blocking=True,
                    stage="request_alignment",
                    field_path=f"/{family}s",
                    message=f"SkillKit introduces a forbidden {family} mechanic family.",
                )
            )
        for entry_index, entry in enumerate(candidate.entries):
            for protocol_index, protocol in enumerate(entry.protocols):
                trigger = protocol.when
                if trigger is None or trigger.subject is None:
                    continue
                if trigger.subject.kind in {"ally", "team"} and (
                    not trigger.subject.selector or trigger.event is None
                ):
                    findings.append(
                        EvaluationFinding(
                            validator_id=self.validator_id,
                            code="TRIGGER_SUBJECT_AMBIGUOUS",
                            severity="WARNING",
                            blocking=False,
                            stage="request_alignment",
                            field_path=f"/entries/{entry_index}/protocols/{protocol_index}/when",
                            message="SkillKit trigger subject or event is ambiguous.",
                        )
                    )
        self._append_mechanic_findings(findings, skill_context, candidate)
        self._append_role_finding(findings, skill_context, candidate)
        unique = []
        seen = set()
        for finding in findings:
            key = (finding.code, finding.field_path, finding.severity, finding.blocking)
            if key in seen:
                continue
            seen.add(key)
            unique.append(finding)
        findings[:] = unique

    @staticmethod
    def _effect_locations(candidate):
        locations = {}
        protocols = {}
        for entry in candidate.entries:
            for protocol in entry.protocols:
                protocol_id = f"{entry.ability_id}/{protocol.protocol_id}"
                protocols[protocol_id] = protocol
                for effect in protocol.causes:
                    locations[
                        f"{entry.ability_id}/{protocol.protocol_id}/{effect.effect_id}"
                    ] = (protocol, effect)
        return protocols, locations

    @staticmethod
    def _ref_is_live(reference, protocols, effects, candidate) -> bool:
        if reference.kind == "protocol":
            return reference.id in protocols
        if reference.kind == "effect":
            return reference.id in effects
        if reference.kind == "resource":
            return any(item.resource_id == reference.id for item in candidate.resources)
        if reference.kind == "state":
            return any(item.state_id == reference.id for item in candidate.states)
        if reference.kind == "summon":
            return any(item.summon_id == reference.id for item in candidate.summons)
        return False

    @classmethod
    def _append_mechanic_findings(cls, findings, skill_context, candidate) -> None:
        requirements = skill_context.intent.mechanic_requirements
        if not requirements:
            return
        protocols, effects = cls._effect_locations(candidate)
        for requirement in requirements:
            matches = []
            for entry_index, entry in enumerate(candidate.entries):
                for protocol_index, protocol in enumerate(entry.protocols):
                    trigger = protocol.when
                    if trigger is None or trigger.subject is None:
                        continue
                    if trigger.subject.kind not in requirement.trigger.subject_kinds:
                        continue
                    if trigger.event not in requirement.trigger.events:
                        continue
                    if requirement.trigger.source_kinds:
                        source = trigger.source_ref
                        if (
                            source is None
                            or source.kind not in requirement.trigger.source_kinds
                            or not cls._ref_is_live(source, protocols, effects, candidate)
                        ):
                            continue
                    for effect in protocol.causes:
                        if effect.subject is None:
                            continue
                        if effect.subject.kind not in requirement.effect.subject_kinds:
                            continue
                        if effect.operation not in requirement.effect.operations:
                            continue
                        if requirement.effect.object_kinds:
                            object_ref = effect.object_ref
                            if (
                                object_ref is None
                                or object_ref.kind not in requirement.effect.object_kinds
                                or not cls._ref_is_live(
                                    object_ref, protocols, effects, candidate
                                )
                            ):
                                continue
                        matches.append((entry_index, protocol_index, protocol, effect))
            if not matches:
                findings.append(
                    EvaluationFinding(
                        validator_id="request_alignment",
                        code="MECHANIC_SKELETON_ABSENT",
                        severity="ERROR",
                        blocking=True,
                        stage="request_alignment",
                        field_path="/entries",
                        message="Requested mechanic has no matching causal skeleton.",
                    )
                )
                continue
            if requirement.feedback.required and not any(
                cls._feedback_matches(
                    relation,
                    source_protocol,
                    source_effect,
                    requirement,
                    protocols,
                    effects,
                    candidate,
                )
                for relation in candidate.feedback_relations
                for _, _, source_protocol, source_effect in matches
            ):
                findings.append(
                    EvaluationFinding(
                        validator_id="request_alignment",
                        code="REQUESTED_MECHANIC_UNREPRESENTED",
                        severity="WARNING",
                        blocking=False,
                        stage="request_alignment",
                        field_path="/feedback_relations/-",
                        message="Requested mechanic lacks a compliant feedback relation.",
                    )
                )

    @classmethod
    def _feedback_matches(
        cls,
        relation,
        source_protocol,
        source_effect,
        requirement,
        protocols,
        effects,
        candidate,
    ) -> bool:
        if relation.source_effect.kind != "effect":
            return False
        source_id = next(
            (
                effect_id
                for effect_id, (_, effect) in effects.items()
                if effect is source_effect
            ),
            None,
        )
        if source_id is None or relation.source_effect.id != source_id:
            return False
        if relation.target_protocol.kind != "protocol":
            return False
        target = protocols.get(relation.target_protocol.id)
        if target is None:
            return False
        source_protocol_id = next(
            (protocol_id for protocol_id, protocol in protocols.items() if protocol is source_protocol),
            None,
        )
        if source_protocol_id == relation.target_protocol.id:
            return False
        target_trigger = target.when
        if (
            target_trigger is None
            or target_trigger.event != "feedback_received"
            or target_trigger.source_ref != relation.source_effect
        ):
            return False
        if relation.event not in requirement.feedback.events:
            return False
        if relation.operation not in requirement.feedback.operations:
            return False
        source_subject = source_effect.subject
        target_subject = target_trigger.subject
        if (
            source_subject is None
            or target_subject is None
            or source_subject.kind != target_subject.kind
        ):
            return False
        if source_subject.kind == "summon" and source_subject.entity_ref != target_subject.entity_ref:
            return False
        downstream = {
            "enables": {
                "direct_output",
                "follow_up_output",
                "ally_enablement",
                "recover_or_mitigate",
                "enemy_action_control",
                "threat_protection",
                "resource_gain",
                "state_enter",
                "summon_spawn",
            },
            "modifies": {
                "direct_output",
                "follow_up_output",
                "ally_enablement",
                "recover_or_mitigate",
                "enemy_action_control",
                "threat_protection",
                "resource_transform",
                "state_apply",
                "summon_act",
            },
            "terminates": {
                "resource_clear",
                "state_exit",
                "state_replace",
                "summon_exit",
                "summon_replace",
            },
        }
        for effect in target.causes:
            if effect.operation not in downstream.get(relation.operation, set()):
                continue
            expected_kind = {
                "resource_gain": "resource",
                "resource_transform": "resource",
                "resource_clear": "resource",
                "state_enter": "state",
                "state_apply": "state",
                "state_exit": "state",
                "state_replace": "state",
                "summon_spawn": "summon",
                "summon_act": "summon",
                "summon_exit": "summon",
                "summon_replace": "summon",
            }.get(effect.operation)
            if expected_kind is None:
                return True
            if (
                effect.object_ref is not None
                and effect.object_ref.kind == expected_kind
                and cls._ref_is_live(effect.object_ref, protocols, effects, candidate)
            ):
                return True
        return False

    @staticmethod
    def _append_role_finding(findings, skill_context, candidate) -> None:
        profile = skill_context.combat_role_profile
        if profile is None:
            return
        if isinstance(profile, Mapping):
            primary = profile.get("primary_role")
            secondary = tuple(profile.get("secondary_roles", ()))
        else:
            primary = getattr(profile, "primary_role", None)
            secondary = tuple(getattr(profile, "secondary_roles", ()))
        requested = []
        if primary is not None:
            requested.append((primary, "core"))
        requested.extend((role, "secondary") for role in secondary)
        if not requested:
            return

        effect_locations = {}
        for entry in candidate.entries:
            for protocol in entry.protocols:
                for effect in protocol.causes:
                    effect_locations[f"{entry.ability_id}/{protocol.protocol_id}/{effect.effect_id}"] = (
                        protocol,
                        effect,
                    )
        for role, centrality in requested:
            row = _ROLE_ROWS.get(role)
            if row is None:
                findings.append(
                    EvaluationFinding(
                        validator_id="request_alignment",
                        code="ROLE_EFFECT_MISMATCH",
                        severity="ERROR",
                        blocking=True,
                        stage="request_alignment",
                        field_path="/role_evidence",
                        message="SkillKit role evidence does not prove the requested role.",
                    )
                )
                return
            valid = False
            for evidence in candidate.role_evidence:
                if evidence.centrality != centrality:
                    continue
                for reference in evidence.effect_refs:
                    if reference.kind != "effect":
                        continue
                    location = effect_locations.get(reference.id)
                    if location is None:
                        continue
                    protocol, effect = location
                    trigger = protocol.when
                    if trigger is None or trigger.subject is None:
                        continue
                    if (
                        effect.operation == row["operation"]
                        and effect.subject is not None
                        and effect.subject.kind in row["subjects"]
                        and (trigger.subject.kind, trigger.event) in row["triggers"]
                    ):
                        valid = True
                        break
                if valid:
                    break
            if not valid:
                findings.append(
                    EvaluationFinding(
                        validator_id="request_alignment",
                        code="ROLE_EFFECT_MISMATCH",
                        severity="ERROR",
                        blocking=True,
                        stage="request_alignment",
                        field_path="/role_evidence",
                        message="SkillKit role evidence does not prove the requested role.",
                    )
                )
                return


__all__ = ["RequestAlignmentValidator"]
