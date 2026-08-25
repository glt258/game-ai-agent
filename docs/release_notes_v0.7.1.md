# v0.7.1 Release Notes

`v0.7.1` is a safety and observability release for Character Authoring Live.
It keeps the pipeline fail-closed while making bounded failure reasons and
sanitized audit metadata useful for diagnosis.

## Included

- Safe Live failure rendering with provider/model metadata, invocation outcome,
  failure phase, grounding check, and allowlisted Canon ID details.
- Strict finalization termination: only the exact `FINALIZE` signal can end the
  authoring loop; tool calls retain precedence and round exhaustion remains
  fail-closed.
- Clean finalization context built from the request and validated evidence,
  without replaying retrieval tool history into the finalization request.
- Observation-grounded evidence and one shared final source set across
  finalization, grounding, recovery, result, and audit paths.
- Deterministic negation-aware Canon forbidden-pattern matching for common
  Chinese negative expressions, while positive RULE-008 violations remain
  rejected.
- CharacterDraft contract recovery audit diagnostics are now fixed and
  exception-class based. Raw provider responses, prompts, model output, and
  secrets are not copied into `error_message`.

## Safety boundaries

- Canon Checker, grounding validation, CharacterDraft validation, Repair, and
  fail-closed behavior remain enabled.
- Provider profile, model, timeout, retry, backoff, and OpenCode configuration
  are unchanged.
- No hallucinated Canon ID is accepted and no CharacterDraft or Canon result is
  fabricated after an incomplete Live pipeline.

## Known limitation

DeepSeek Pro full finalization requests can still exceed the existing bounded
provider attempts. That provider/model latency issue is documented and is not
silently changed by this release.

## Manual publication checks

Run the release validation commands from the repository root, verify the
generated `dist/` artifacts, then publish the commit and tag manually as
`v0.7.1`. Do not publish a Live API key or captured raw provider payloads.
