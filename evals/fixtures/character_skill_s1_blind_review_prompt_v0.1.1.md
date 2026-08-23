# Character Skill Interface v0.1.1 — CS-S1 Blind Review Prompt

You are an independent reviewer of a structured character-skill interface.
The review package contains this prompt plus two semantic inputs:

1. `evals/fixtures/character_skill_interface_prototype_cases_v0.1.1.public.json`
2. `evals/fixtures/character_skill_s1_blind_review_output_schema_v0.1.1.json`

The semantic inputs are only the public case fixture and the output schema. The
prompt itself is included in the package for provenance and response
reproducibility; it is not an additional semantic case input. The first file
contains the complete set of nineteen review cases. The second file defines
the JSON shape of your response. Treat the case bytes as the review record: do
not add facts that are not represented by a case, and do not silently repair a
candidate while judging it.

## Review vocabulary

- A **candidate** is a structured skill kit. Its `entries` contain abilities;
  each ability has protocols, and each protocol has a `when` trigger and zero
  or more `causes` effects.
- A trigger records a typed subject, an event, and optional source or qualifier
  information. An effect records a typed subject, an operation, an optional
  typed object reference, and a description.
- A typed reference is an object with a `kind` and an `id`. References must
  resolve within the namespace named by their kind. Do not treat a bare string
  as an equivalent reference.
- `feedback_relations` connect a source effect to a target protocol and record
  the feedback event and operation. Check that each relation is attached to a
  real causal path rather than merely being present.
- `resources`, `states`, and `summons` describe lifecycle leases. Their
  relation arrays point to effects that open, use, establish, apply, end,
  spawn, act, depart, or replace the corresponding lease. Check the full
  lifecycle represented by the case.
- `role_evidence` associates effects with a centrality label. A
  `combat_role_profile` contains a primary role and optional secondary roles.
  Judge role evidence from the concrete effect subjects and operations.
- `context.intent` may contain mechanic requirements, forbidden mechanic
  families, and hard-constraint conflicts. A mechanic requirement describes
  the trigger subject/event, effect subject/operation, and (when required) a
  feedback event/operation. All of these constraints are part of the case.
- `reference_review_context`, when present, is metadata supplied with the
  case. Use it only as represented in the input; do not fetch or assume any
  external record.

## Decision standard

Assign one verdict to every case:

- `PASS`: the candidate expresses the requested interface semantics with
  resolvable references, complete required lifecycle or feedback structure,
  and no blocking ambiguity or conflict. Set `primary_finding` exactly to
  `NONE`.
- `REPAIR`: a concrete causal skeleton is present, and the remaining defect can
  be corrected at a bounded, identifiable location while preserving the core
  design. Include a repair plan naming what to preserve and what to change.
- `FAIL`: a required core skeleton is absent, constraints conflict, a forbidden
  mechanic is introduced, or the correction would require redesign rather
  than a bounded local change.

Use the case's concrete fields to justify the decision. A short primary code
for `REPAIR` or `FAIL` must be a non-`NONE` uppercase underscore-separated
string describing the main evidence; derive it independently for each case.
Do not assign a preselected code or verdict to a case.

## Required review passes

For every case, inspect:

1. Whether all typed references resolve and whether subjects, events,
   operations, and objects form a concrete trigger-to-effect relation.
2. Whether resource, state, summon, and feedback relationships are complete
   where the case declares them, including exit, replacement, or reset paths.
3. Whether the candidate satisfies the role profile and intent constraints
   without relying on prose, implicit defaults, or unrepresented metadata.
4. Whether each required interface field is generatable by an ordinary
   provider response from the fields shown. Report an interface risk when a
   field is ambiguous, untyped, unresolvable, or cannot be emitted without
   hidden information.
5. Whether a proposed repair is local and replayable: preserve existing valid
   anchors, identify the smallest affected paths, and avoid inventing a new
   mechanism family or taxonomy. If that cannot be done, use `FAIL`.

Pay special attention to these boundaries:

- Review `case_13` and `case_19` as strictly separate cases. Analyze each
  trigger, effect, and feedback path from its own fields. Do not transfer a
  conclusion, finding code, or repair plan from one case to the other.
- Review `case_14` fail-closed. Read the supplied role values literally. Do not
  auto-normalize unsupported labels, aliases, or mixed profile values into a
  different accepted role; do not infer a role that is not represented by the
  interface.
- Check that provider-facing fields are actually generatable and that typed
  references remain stable after serialization and parsing. A descriptive
  name alone is not a substitute for a typed field.
- Check for accidental numerical balance requirements such as damage values,
  cooldown tuning, percentages, or probabilities when the case only asks for
  interface semantics. Do not introduce a second role taxonomy, alternate
  role names, or an extra classification system to make a candidate appear to
  fit.

## Response contract

Return one JSON object and no surrounding prose. Follow the output schema
exactly:

- `schema_version` is the schema version declared in the schema file.
- `source_commit` is supplied by the caller and must be the full lowercase
  forty-hex identifier of the frozen input commit; never invent or shorten it.
- `reviewer` is exactly the model identifier assigned by the caller.
- `input_files` records the lowercase SHA-256 digest for each of the three
  package files: the public case fixture, this prompt, and the output schema.
  The caller should calculate these digests from raw file bytes. The semantic
  inputs used for judgment remain only the public case fixture and output
  schema.
- `provenance` contains the provider, requested and reported model names,
  generation timestamp, public request identifier (or a redacted marker),
  and a description of any syntax-only normalization. Do not alter a verdict,
  reason, code, or repair plan during normalization.
- `results` contains exactly nineteen entries in the fixture order,
  `case_01` through `case_19`, with one entry per case.
- Every result contains `case_id`, `verdict`, `primary_finding`, and a
  non-empty `reason`. A `PASS` result uses `NONE` as its
  `primary_finding`; `REPAIR` and `FAIL` results use a non-`NONE` evidence
  code. A `REPAIR` result must contain `repair_plan` with
  non-empty string arrays `preserve` and `changes`; `PASS` and `FAIL` results
  must omit `repair_plan`. `interface_risks` and
  `provider_difficulty` are optional and must follow the schema.

Keep reasons evidence-based and case-local. Do not include material from any
input other than the public fixture and the output schema.
