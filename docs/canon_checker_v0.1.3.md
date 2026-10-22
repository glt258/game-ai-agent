# Canon Checker v0.1.3 — Live Variant Hardening

## Live re-acceptance findings

Hermes re-probes left two deterministic false-positive families after v0.1.2:
complex denial around forbidden institution creation, and natural proposal
language involving an existing Canon target. This patch remains offline-only
and changes only the read-only Canon Checker contract.

## Complex forbidden denial

Forbidden institution detection now evaluates the polarity of the introduction
action itself. The action is separated from later entity properties:

```text
未新增 [任何不对外公开的秘密监管机构]
新增 [一个不对外公开的秘密监管机构]
```

The first is a negative creation claim and does not produce Forbidden, World
Rule, or Hard Constraint findings. The second is a positive creation claim and
remains blocked. Mixed clauses are local, so a negative first clause cannot
hide a later positive creation. A secret centralized institution described
without an introduction action remains covered by the existing RULE-008
detector.

Introduction actions include `新增`, `引入`, `建立`, `设立`, `成立`, `创建`,
`组建`, `搭建`, `设置`, and `新设`. Hedged creation such as “曾考虑创建” is
not treated as an established creation claim when followed by a final negative
establishment claim.

## Existing Canon entity vs relation / membership / assignment

`CANON_PRESENTED_AS_PROPOSAL` now prioritizes explicit entity-introduction
markers such as:

```text
新增角色 / 新设计 / 新组织 / 新部门 / 新事件 / 新机构
```

An existing entity with such a marker remains an error. Without an introduction
marker, natural interaction context is accepted even when it does not use a
specific relationship verb, for example “未来可能采访余弦”. Existing faction
divisions are included in the read-only Canon entity inventory, so creating
“新部门：回写与社会认知组” remains blocked while assigning a new task inside
that division is allowed.

Direct or ambiguous existing-entity-only mentions remain fail-closed. The
proposal checker still separately evaluates whether a proposed relation is
later presented as an accomplished fact through `PROPOSAL_PRESENTED_AS_CANON`.

## Regression matrix

The public `CanonChecker.check()` seam is covered by:

```text
py -m pytest -q tests/test_canon_checker_live_language.py
```

The offline Live-derived runner contains 38 cases:

```text
py scripts/run_canon_checker_live_language_evals.py
```

The matrix includes complex denial/action-property pairs, mixed clauses,
natural interaction variants, faction-division assignments, introduction
markers, H1 existing-entity protection, and proposal-presented-as-Canon
protection.

## H2 unchanged

`canon_basis.supports` remains a deterministic extractive support contract.
This patch does not add semantic similarity, embeddings, an LLM judge, or a
paraphrase resolver. Non-extractive paraphrases may still produce
`UNSUPPORTED_CANON_CLAIM` by design.
