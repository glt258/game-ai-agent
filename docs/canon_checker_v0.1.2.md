# Canon Checker v0.1.2 — Live Language Hardening

## Why this patch was needed

Hermes Live acceptance exposed deterministic false positives in three narrow
areas: negated forbidden claims, negated Lore access claims, and proposed
relations that mentioned an existing Canon target. This patch changes only the
read-only `CanonChecker` precision rules and adds offline regressions derived
from the minimal Live reproductions.

## Clause-local polarity

The checker now separates sentence clauses and uses the smallest useful local
claim context. It does not implement a Chinese parser or general semantic
understanding. Shared local polarity primitives are reused by the forbidden
and knowledge guards, while each rule keeps its own interpretation of what a
negated claim means.

## Forbidden negation semantics

Claims such as “未新增秘密政府组织” and “没有建立秘密监管机构” are treated
as negative existence/action claims and do not trigger the forbidden rule. A
later positive clause remains visible: “没有公开身份，但实际上新增了秘密政府
监管机构” still fails. Secrecy properties such as “不对外公开的行政机构统一
监管全市能力者” remain positive institutional claims and still fail RULE-008.

## Knowledge negation semantics

Non-public Lore is checked only when the same sentence context contains an
access or knowledge predicate. Preposed negation, parenthesized Lore IDs, and
postposed negation are supported, including “不了解 lore_011” and “lore_025，
角色对此无访问权”. Mixed-polarity claims are evaluated per local clause, so
one denied Lore does not immunize a later positive access claim. The previous
fixed eight-character window is no longer the primary decision mechanism.

## Existing Canon target vs proposed relation

The proposal guard distinguishes:

- an existing entity directly introduced as new, which remains an error;
- a relation to an existing character, which is allowed when the structure is
  expressed with a relation lead such as “与” or “向”;
- a membership or assignment inside an existing organization, which is allowed
  when expressed with “在”, “进入”, “加入”, or “作为”.

Ambiguous mentions remain fail-closed. The rule does not attempt to maintain an
unbounded relationship-verb whitelist.

## Regression strategy

The public `CanonChecker.check()` seam is covered by:

```text
py -m pytest -q tests/test_canon_checker_live_language.py
```

The offline Live-derived matrix is:

```text
py scripts/run_canon_checker_live_language_evals.py
```

It includes 19 minimal cases with positive/negative pairs for each repaired
claim class. Existing Canon red-team coverage remains 22/23 with H2 as the
single known limitation.

## H2 unchanged

`canon_basis.supports` remains a deterministic extractive support contract.
This patch does not add semantic similarity, embeddings, an LLM judge, or a
paraphrase resolver. Non-extractive paraphrases may still produce
`UNSUPPORTED_CANON_CLAIM` by design.

## Remaining limitations

The clause helper is intentionally conservative and lexical. It is not a
complete natural-language parser, and ambiguous proposal wording remains
fail-closed for human review.
