"""Run or plan the CS-S2 shadow evidence cohort."""

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

from evals.character_skill_s2_shadow_evidence import (  # noqa: E402
    CompactContractV2Runner,
    ContractComplianceCohortRunner,
    EnumExpansionStepdownRunner,
    EvidenceRunnerError,
    FixedContractComplianceCohortRunner,
    FullInputTinyOutputRunner,
    MinimalSkillKitRunner,
    MinimalTransportSanityRunner,
    ModelSuitabilityProbeRunner,
    NestedShapeStepdownRunner,
    O1SafeDiagnosticRunner,
    O2LocalStructureRunner,
    OutputStepdownRunner,
    RetryUnavailableCohortRunner,
    ShadowEvidenceRunner,
    ShapeDiagnosticCohortRunner,
    TimeoutSuitabilityProbeRunner,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reproducible CS-S2 SkillKit shadow evidence runner (dry-run by default)"
    )
    parser.add_argument("--live", action="store_true", help="opt into the bounded provider run")
    parser.add_argument("--dry-run", action="store_true", help="explicitly request the default plan-only mode")
    parser.add_argument("--repeat", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--resume", action="store_true", help="resume an existing append-only result bundle")
    parser.add_argument(
        "--retry-unavailable-from",
        type=Path,
        default=None,
        help="plan or run an independent retry cohort from an existing evidence bundle",
    )
    parser.add_argument(
        "--shape-diagnostic-from",
        type=Path,
        default=None,
        help="plan or run the single case_13 content-free shape diagnostic cohort",
    )
    parser.add_argument(
        "--contract-compliance-from",
        type=Path,
        default=None,
        help="plan or run the single case_13 contract-compliance cohort",
    )
    parser.add_argument(
        "--fixed-contract-compliance-from",
        type=Path,
        default=None,
        help="plan or append one sample to a fixed multi-observation contract-compliance cohort",
    )
    parser.add_argument(
        "--target-samples",
        type=int,
        default=None,
        help="fixed cohort target sample count (frozen after initialization)",
    )
    parser.add_argument(
        "--append-next-sample",
        action="store_true",
        help="explicitly authorize one live fixed-cohort sample append",
    )
    parser.add_argument(
        "--timeout-suitability-probe",
        "--timeout-suitability",
        action="store_true",
        help="run or plan the isolated case_13 60-second timeout-suitability probe",
    )
    parser.add_argument(
        "--model-suitability-probe",
        "--deepseek-v4-pro-bakeoff",
        action="store_true",
        help="run or plan the isolated case_13 DeepSeek V4 Pro model-suitability probe",
    )
    parser.add_argument(
        "--minimal-transport-sanity",
        "--minimal-transport-sanity-probe",
        action="store_true",
        help="run or plan the isolated tiny JSON OpenCode Go transport sanity probe",
    )
    parser.add_argument(
        "--full-input-tiny-output",
        "--full-input-tiny-output-probe",
        action="store_true",
        help="run or plan the isolated full-input tiny-output latency probe",
    )
    parser.add_argument(
        "--enum-expansion-stepdown",
        action="store_true",
        help="run or plan the isolated L1 no-enum tiny-output diagnostic probe",
    )
    parser.add_argument(
        "--nested-shape-stepdown",
        "--l2-shape-stepdown",
        "--l2-root-minimal-shape",
        action="store_true",
        help="run or plan the isolated L2 root-plus-minimal-shape diagnostic probe",
    )
    parser.add_argument(
        "--compact-contract-v2",
        "--v2-a",
        action="store_true",
        help="plan the offline-only Compact SkillKit Contract V2-A gate",
    )
    parser.add_argument(
        "--minimal-skillkit",
        "--minimal-legal-skillkit",
        action="store_true",
        help="plan or run the independent V2-A minimal legal SkillKit probe",
    )
    parser.add_argument(
        "--o1-root-only",
        "--output-stepdown-o1",
        action="store_true",
        help="plan or run the independent V2-A O1 canonical root-only probe",
    )
    parser.add_argument(
        "--o1-safe-diagnostic",
        "--o1-diagnostic",
        action="store_true",
        help="plan or run the independent O1 safe parser-diagnostic cohort",
    )
    parser.add_argument(
        "--o1-schema-guided-diagnostic",
        action="store_true",
        help="plan or run the independent O1 diagnostic with selective canonical schema guidance",
    )
    parser.add_argument(
        "--o2-local-structure",
        action="store_true",
        help="plan or run the independent O2 local-structure cohort",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="timeout suitability probe timeout (frozen at 60)",
    )
    parser.add_argument(
        "--max-transport-retries",
        type=int,
        default=None,
        help="probe retries (defaults to 2, or 0 for minimal transport sanity)",
    )
    parser.add_argument(
        "--probe-source-commit",
        default=None,
        help="exact implementation commit required before a live timeout probe",
    )
    parser.add_argument("--output", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--manifest", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    timeout_seconds = 60 if args.timeout_seconds is None else args.timeout_seconds
    max_transport_retries = (
        (0 if (args.minimal_transport_sanity or args.full_input_tiny_output or args.enum_expansion_stepdown or args.nested_shape_stepdown or args.compact_contract_v2 or args.minimal_skillkit or args.o1_root_only or args.o1_safe_diagnostic or args.o1_schema_guided_diagnostic or args.o2_local_structure) else 2)
        if args.max_transport_retries is None
        else args.max_transport_retries
    )
    target_samples = args.target_samples
    if target_samples is None:
        target_samples = 1 if (args.timeout_suitability_probe or args.model_suitability_probe or args.minimal_transport_sanity or args.full_input_tiny_output or args.enum_expansion_stepdown or args.nested_shape_stepdown or args.compact_contract_v2 or args.minimal_skillkit or args.o1_root_only or args.o1_safe_diagnostic or args.o1_schema_guided_diagnostic or args.o2_local_structure) else 3
    if args.live and args.dry_run:
        print(json.dumps({"status": "error", "error_code": "MODE_ARGUMENTS_INVALID"}))
        return 2
    if args.retry_unavailable_from is not None and args.case_ids is not None and not args.case_ids:
        print(json.dumps({"status": "error", "error_code": "RETRY_ARGUMENTS_INVALID"}))
        return 2
    if args.shape_diagnostic_from is not None and (args.retry_unavailable_from is not None or args.case_ids not in (None, ["case_13"])):
        print(json.dumps({"status": "error", "error_code": "DIAGNOSTIC_ARGUMENTS_INVALID"}))
        return 2
    if args.contract_compliance_from is not None and (args.retry_unavailable_from is not None or args.shape_diagnostic_from is not None or args.case_ids not in (None, ["case_13"])):
        print(json.dumps({"status": "error", "error_code": "COMPLIANCE_ARGUMENTS_INVALID"}))
        return 2
    if args.fixed_contract_compliance_from is not None and (
        args.retry_unavailable_from is not None
        or args.shape_diagnostic_from is not None
        or args.contract_compliance_from is not None
        or args.case_ids not in (None, ["case_13"])
    ):
        print(json.dumps({"status": "error", "error_code": "FIXED_COHORT_ARGUMENTS_INVALID"}))
        return 2
    if args.timeout_suitability_probe and (
        args.retry_unavailable_from is not None
        or args.shape_diagnostic_from is not None
        or args.contract_compliance_from is not None
        or args.fixed_contract_compliance_from is not None
        or args.case_ids not in (None, ["case_13"])
        or args.repeat != 1
        or args.append_next_sample
        or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "TIMEOUT_SUITABILITY_ARGUMENTS_INVALID"}))
        return 2
    if args.model_suitability_probe and (
        args.timeout_suitability_probe
        or args.retry_unavailable_from is not None
        or args.shape_diagnostic_from is not None
        or args.contract_compliance_from is not None
        or args.fixed_contract_compliance_from is not None
        or args.case_ids not in (None, ["case_13"])
        or args.repeat != 1
        or args.append_next_sample
        or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "MODEL_SUITABILITY_ARGUMENTS_INVALID"}))
        return 2
    if args.minimal_transport_sanity and (
        args.timeout_suitability_probe
        or args.model_suitability_probe
        or args.retry_unavailable_from is not None
        or args.shape_diagnostic_from is not None
        or args.contract_compliance_from is not None
        or args.fixed_contract_compliance_from is not None
        or args.case_ids is not None
        or args.repeat != 1
        or args.append_next_sample
        or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "MINIMAL_TRANSPORT_SANITY_ARGUMENTS_INVALID"}))
        return 2
    if args.full_input_tiny_output and (
        args.timeout_suitability_probe
        or args.model_suitability_probe
        or args.minimal_transport_sanity
        or args.retry_unavailable_from is not None
        or args.shape_diagnostic_from is not None
        or args.contract_compliance_from is not None
        or args.fixed_contract_compliance_from is not None
        or args.case_ids is not None
        or args.repeat != 1
        or args.append_next_sample
        or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "FULL_INPUT_TINY_OUTPUT_ARGUMENTS_INVALID"}))
        return 2
    if args.enum_expansion_stepdown and (
        args.timeout_suitability_probe
        or args.model_suitability_probe
        or args.minimal_transport_sanity
        or args.full_input_tiny_output
        or args.retry_unavailable_from is not None
        or args.shape_diagnostic_from is not None
        or args.contract_compliance_from is not None
        or args.fixed_contract_compliance_from is not None
        or args.case_ids is not None
        or args.repeat != 1
        or args.append_next_sample
        or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "ENUM_STEPDOWN_ARGUMENTS_INVALID"}))
        return 2
    if args.nested_shape_stepdown and (
        args.timeout_suitability_probe
        or args.model_suitability_probe
        or args.minimal_transport_sanity
        or args.full_input_tiny_output
        or args.enum_expansion_stepdown
        or args.retry_unavailable_from is not None
        or args.shape_diagnostic_from is not None
        or args.contract_compliance_from is not None
        or args.fixed_contract_compliance_from is not None
        or args.case_ids is not None
        or args.repeat != 1
        or args.append_next_sample
        or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "NESTED_SHAPE_STEPDOWN_ARGUMENTS_INVALID"}))
        return 2
    if args.compact_contract_v2 and (
        args.timeout_suitability_probe or args.model_suitability_probe or args.minimal_transport_sanity
        or args.full_input_tiny_output or args.enum_expansion_stepdown or args.nested_shape_stepdown
        or args.retry_unavailable_from is not None or args.shape_diagnostic_from is not None
        or args.contract_compliance_from is not None or args.fixed_contract_compliance_from is not None
        or args.case_ids is not None or args.repeat != 1 or args.append_next_sample
        or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "COMPACT_V2_ARGUMENTS_INVALID"}))
        return 2
    if args.minimal_skillkit and (
        args.timeout_suitability_probe or args.model_suitability_probe or args.minimal_transport_sanity
        or args.full_input_tiny_output or args.enum_expansion_stepdown or args.nested_shape_stepdown
        or args.compact_contract_v2 or args.retry_unavailable_from is not None
        or args.shape_diagnostic_from is not None or args.contract_compliance_from is not None
        or args.fixed_contract_compliance_from is not None or args.case_ids not in (None, ["case_13"])
        or args.repeat != 1 or args.append_next_sample
        or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "MINIMAL_SKILLKIT_ARGUMENTS_INVALID"}))
        return 2
    if args.o1_root_only and (
        args.timeout_suitability_probe or args.model_suitability_probe or args.minimal_transport_sanity
        or args.full_input_tiny_output or args.enum_expansion_stepdown or args.nested_shape_stepdown
        or args.compact_contract_v2 or args.minimal_skillkit or args.retry_unavailable_from is not None
        or args.shape_diagnostic_from is not None or args.contract_compliance_from is not None
        or args.fixed_contract_compliance_from is not None or args.case_ids not in (None, ["case_13"])
        or args.repeat != 1 or args.append_next_sample or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "O1_ROOT_ONLY_ARGUMENTS_INVALID"}))
        return 2
    if args.o1_safe_diagnostic and (
        args.timeout_suitability_probe or args.model_suitability_probe or args.minimal_transport_sanity
        or args.full_input_tiny_output or args.enum_expansion_stepdown or args.nested_shape_stepdown
        or args.compact_contract_v2 or args.minimal_skillkit or args.o1_root_only
        or args.retry_unavailable_from is not None or args.shape_diagnostic_from is not None
        or args.contract_compliance_from is not None or args.fixed_contract_compliance_from is not None
        or args.case_ids not in (None, ["case_13"]) or args.repeat != 1 or args.append_next_sample
        or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "O1_SAFE_DIAGNOSTIC_ARGUMENTS_INVALID"}))
        return 2
    if args.o1_schema_guided_diagnostic and (
        args.timeout_suitability_probe or args.model_suitability_probe or args.minimal_transport_sanity
        or args.full_input_tiny_output or args.enum_expansion_stepdown or args.nested_shape_stepdown
        or args.compact_contract_v2 or args.minimal_skillkit or args.o1_root_only or args.o1_safe_diagnostic
        or args.retry_unavailable_from is not None or args.shape_diagnostic_from is not None
        or args.contract_compliance_from is not None or args.fixed_contract_compliance_from is not None
        or args.case_ids not in (None, ["case_13"]) or args.repeat != 1 or args.append_next_sample
        or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "O1_SCHEMA_GUIDED_ARGUMENTS_INVALID"}))
        return 2
    if args.o2_local_structure and (
        args.timeout_suitability_probe or args.model_suitability_probe or args.minimal_transport_sanity
        or args.full_input_tiny_output or args.enum_expansion_stepdown or args.nested_shape_stepdown
        or args.compact_contract_v2 or args.minimal_skillkit or args.o1_root_only or args.o1_safe_diagnostic
        or args.o1_schema_guided_diagnostic or args.retry_unavailable_from is not None
        or args.shape_diagnostic_from is not None or args.contract_compliance_from is not None
        or args.fixed_contract_compliance_from is not None or args.case_ids not in (None, ["case_13"])
        or args.repeat != 1 or args.append_next_sample or (args.target_samples is not None and args.target_samples != 1)
    ):
        print(json.dumps({"status": "error", "error_code": "O2_LOCAL_STRUCTURE_ARGUMENTS_INVALID"}))
        return 2
    if args.append_next_sample and args.fixed_contract_compliance_from is None:
        print(json.dumps({"status": "error", "error_code": "FIXED_COHORT_ARGUMENTS_INVALID"}))
        return 2
    try:
        if args.fixed_contract_compliance_from is not None:
            runner = FixedContractComplianceCohortRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                source_path=args.fixed_contract_compliance_from,
                live=args.live,
                target_sample_count=target_samples,
                resume=args.resume,
                append_next_sample=args.append_next_sample,
                output_path=args.output,
            )
        elif args.timeout_suitability_probe:
            runner = TimeoutSuitabilityProbeRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                live=args.live,
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_samples,
                expected_source_commit=args.probe_source_commit,
                resume=args.resume,
                output_path=args.output,
            )
        elif args.model_suitability_probe:
            runner = ModelSuitabilityProbeRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                live=args.live,
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_samples,
                expected_source_commit=args.probe_source_commit,
                resume=args.resume,
                output_path=args.output,
            )
        elif args.minimal_transport_sanity:
            runner = MinimalTransportSanityRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                live=args.live,
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_samples,
                expected_source_commit=args.probe_source_commit,
                resume=args.resume,
                output_path=args.output,
            )
        elif args.full_input_tiny_output:
            runner = FullInputTinyOutputRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                live=args.live,
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_samples,
                expected_source_commit=args.probe_source_commit,
                resume=args.resume,
                output_path=args.output,
            )
        elif args.enum_expansion_stepdown:
            runner = EnumExpansionStepdownRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                live=args.live,
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_samples,
                expected_source_commit=args.probe_source_commit,
                resume=args.resume,
                output_path=args.output,
            )
        elif args.nested_shape_stepdown:
            runner = NestedShapeStepdownRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                live=args.live,
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_samples,
                expected_source_commit=args.probe_source_commit,
                resume=args.resume,
                output_path=args.output,
            )
        elif args.compact_contract_v2:
            runner = CompactContractV2Runner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                live=args.live,
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_samples,
                expected_source_commit=args.probe_source_commit,
                resume=args.resume,
                output_path=args.output,
            )
        elif args.minimal_skillkit:
            runner = MinimalSkillKitRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                live=args.live,
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_samples,
                expected_source_commit=args.probe_source_commit,
                resume=args.resume,
                output_path=args.output,
            )
        elif args.o1_root_only:
            runner = OutputStepdownRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                live=args.live,
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_samples,
                expected_source_commit=args.probe_source_commit,
                resume=args.resume,
                output_path=args.output,
            )
        elif args.o1_safe_diagnostic or args.o1_schema_guided_diagnostic:
            runner = O1SafeDiagnosticRunner(ROOT, manifest_path=args.manifest, guided=args.o1_schema_guided_diagnostic)
            result = runner.run(
                live=args.live,
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_samples,
                expected_source_commit=args.probe_source_commit,
                resume=args.resume,
                output_path=args.output,
            )
        elif args.o2_local_structure:
            runner = O2LocalStructureRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                live=args.live,
                timeout_seconds=timeout_seconds,
                max_transport_retries=max_transport_retries,
                target_sample_count=target_samples,
                expected_source_commit=args.probe_source_commit,
                resume=args.resume,
                output_path=args.output,
            )
        elif args.contract_compliance_from is not None:
            if args.repeat != 1:
                raise EvidenceRunnerError("COMPLIANCE_REPEAT_INVALID")
            runner = ContractComplianceCohortRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                source_path=args.contract_compliance_from,
                live=args.live,
                output_path=args.output,
            )
        elif args.shape_diagnostic_from is not None:
            if args.repeat != 1:
                raise EvidenceRunnerError("DIAGNOSTIC_REPEAT_INVALID")
            runner = ShapeDiagnosticCohortRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                source_path=args.shape_diagnostic_from,
                live=args.live,
                output_path=args.output,
            )
        elif args.retry_unavailable_from is not None:
            if args.repeat != 1:
                raise EvidenceRunnerError("RETRY_REPEAT_INVALID")
            runner = RetryUnavailableCohortRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                source_path=args.retry_unavailable_from,
                live=args.live,
                case_id=args.case_ids,
                resume=args.resume,
                output_path=args.output,
            )
        else:
            runner = ShadowEvidenceRunner(ROOT, manifest_path=args.manifest)
            result = runner.run(
                live=args.live,
                repeat=args.repeat,
                case_id=args.case_ids,
                resume=args.resume,
                output_path=args.output,
            )
    except EvidenceRunnerError as error:
        print(json.dumps({"status": "blocked", "error_code": error.code}, ensure_ascii=False))
        return 2
    except Exception:
        # The CLI is an evidence boundary: never print provider or environment
        # exception text, even when an integration seam fails unexpectedly.
        print(json.dumps({"status": "blocked", "error_code": "RUNNER_INTERNAL_FAILURE"}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
