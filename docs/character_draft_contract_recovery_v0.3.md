# CharacterDraft Contract Recovery v0.3

## Purpose

Contract recovery handles a provider response that was successfully parsed as
JSON but is not yet a valid `CharacterDraft`. It runs before Canon Checker,
Character Repair, and diversity validation. It is structural completion, not
creative regeneration and not Canon repair.

## Existing semantics

`canon_basis` is an array of model-proposed Canon source entries and may be
explicitly empty when no Canon-backed claim was retrieved. `new_design_elements`
is an array describing new design material and may also be explicitly empty.
Because missing either field is materially different from an explicit empty
array, neither receives a deterministic default. `open_questions` remains the
one existing safe normalization: when it alone is omitted, it becomes `[]`.

## Recovery policy

1. Inspect missing core fields, unknown fields, and invalid known fields.
2. If the known draft is otherwise valid and has unknown fields, discard only
   those fields and record every discarded name in the audit.
3. If core fields are missing and there are no unknown or invalid fields, make
   at most one recovery call through the existing provider-neutral `AgentModel`.
4. Merge only explicitly missing fields. Any attempted overwrite of an
   existing valid field fails closed.
5. Parse and validate the merged draft normally. A failed or incomplete
   recovery is `NOT_COMPLETED`; there is no second attempt.

The recovery prompt receives the original brief, the partial draft, available
Canon source IDs/types, and bounded reference context already available to the
generation step. It does not query new lore or certify Canon truth. Recovered
`canon_basis` entries remain subject to the normal Canon Checker.

## Unknown fields

The schema whitelist remains strict. Unknown fields are not accepted as domain
extensions. The narrow cleanup exception exists only when all core fields and
all known field shapes already validate; otherwise an unknown field is retained
in the diagnosis and the pipeline fails closed. This handles malformed
provider wrappers and artifacts such as an iframe fragment without silently
discarding an incomplete character.

## Audit and boundaries

Generation audit separates `normalized_fields`, `contract_recovery`, and
`model_invocations`. Recovery invocations are marked with purpose
`character_draft_recovery`. The official demo and live failure renderer expose
recovery status and recovered/discarded fields separately from Canon Repair.

Provider timeout/retry behavior is unchanged. There is no live-to-offline
fallback and no generic self-healing loop.

The real post-implementation live samples did not require contract recovery.
Recovery branches are regression-tested, and post-change live pipeline
compatibility was verified; no live sample is claimed as `APPLIED` recovery.
