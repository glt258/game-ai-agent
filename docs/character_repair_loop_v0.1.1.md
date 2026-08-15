# Character Repair Loop v0.1.1 Red-Team Hardening

## Scope

This patch hardens the existing one-attempt repair loop. It does not add a new
provider, a second repair, an LLM judge, or any Canon/Data write.

## Hermes findings fixed

- P0 hard-constraint silent drop: deterministic `HardConstraintDomain` mapping
  plus post-repair preservation checks protect knowledge, authority, story-role,
  relationship, primitive identity, and ability requirements.
- Relationship serialization: `CharacterDraft.to_dict()` no longer calls
  `dataclasses.asdict()` over immutable `MappingProxyType` relationships.
- Hidden supreme authority: command and decision predicates are clause-local;
  a negated title does not cancel a later positive command claim.
- Internal materials: broad quantifier + sensitive object + access verb now
  recognizes internal materials, internal data, restricted materials, personal
  files, and ability files.

## Impossible Brief behavior

If an original draft satisfies a hard requirement that conflicts with Canon,
Repair cannot make it disappear. A candidate that drops that requirement is
rejected with `REPAIR_HARD_CONSTRAINT_VIOLATION`; the recommended draft remains
the original and the workflow remains unresolved.

## Regression commands

```powershell
py -m pytest -q tests/test_character_repair_redteam.py
py scripts/run_character_repair_redteam.py
py scripts/demo_character_repair_v0_1.py --case relationship --json
```

## Known limitations

The H2 extractive `canon_basis.supports` contract remains unchanged. The loop
still permits one semantic repair attempt, performs no semantic minimal-diff
scoring, and never automatically approves or publishes a character.
