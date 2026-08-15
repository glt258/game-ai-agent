# Canon Checker v0.1.1 — Red-Team Hardening

This patch keeps Canon validation deterministic and read-only. The generator
still proposes; `CanonChecker` verifies. No LLM judge, embeddings, fuzzy
similarity, repair loop, Canon write, provider change, or StoryState mutation
is involved.

## Hardened invariants

- Cross-domain authority requires a control action plus at least two
  independent public-safety domains. Coordination and information exchange do
  not imply command authority. Narrative claims such as “temporary
  authorization” are not Canon authorization.
- RULE-008 now recognizes the composition of secrecy, an administrative or
  regulatory entity, and broad centralized ability governance. A non-public
  research project is not sufficient.
- Story-role validation is separate from `story_link` validation. It resolves
  only explicit story/case/incident IDs or registered names in the draft and
  request context, so a generic “事故” is not silently bound to a story.
- RULE-024 rejects a minor's professional high-risk frontline occupation using
  the existing `age` and occupation fields. It does not reject ordinary minor
  work or school life.
- Knowledge overreach requires a universal quantifier, a sensitive object, and
  an access/knowledge verb. A quantifier alone is harmless.
- Elemental Forbidden Patterns require multiple elemental categories and a
  classification/system marker. A bounded heat or fire-like personal effect is
  not automatically forbidden.
- Proposal modality is evaluated within the clause containing the proposed
  phrase. A later hedge cannot hide an earlier accomplished fact.
- `CANON_PRESENTED_AS_PROPOSAL` now emits an `ERROR` when a new-design list
  directly names an existing Canon entity. A new relationship to that entity
  remains allowed.

## H2 known limitation and contract containment

`canon_basis.supports` remains fail-closed for non-extractive paraphrases. For
example, a paraphrase of the established “legal associate profession” fact is
still reported as `UNSUPPORTED_CANON_CLAIM`. This is intentional in v0.1.1:
the checker does not use an unsafe synonym engine or semantic judge. The
character-generation prompt now tells the model to use generic support keys,
field paths, or short extractive excerpts instead of free paraphrase.

## Regression evidence

`evals/canon_checker_redteam.py` defines all 23 red-team IDs (`A`–`F`,
`G1`–`G15`, `H1`–`H2`). The runner is:

```text
py scripts/run_canon_checker_redteam.py
```

The expected post-hardening result is 22 correctly handled cases, no false
negatives, no unexpected false positives, no severity issues, and one explicit
known limitation (`H2`).

## Future work

If support claims need safe paraphrase support, evolve the contract to carry a
structured support key and an optional supporting excerpt. Do not relax the
current extractive and negative-polarity checks without independent positive
and negative regression evidence.
