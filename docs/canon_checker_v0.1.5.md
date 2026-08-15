# Canon Checker v0.1.5 — Compound Absence Scope Hardening

## Hermes v0.6.4 Live finding

The remaining Live false positive was:

```text
无秘密政府机构或秘密行政机构要素
```

The v0.1.4 rule recognized the absence predicate for the first target but
treated the second coordinated target as a new positive forbidden claim.

## Compound absence scope

An explicit absence or non-use predicate now covers a bounded local coordinate
chain using:

```text
或 / 或者 / 与 / 和 / 及 / 以及 / 、 /
```

This supports two- and three-target lists, including:

```text
无 A 或 B
无 A、B 或 C
未使用 A 与 B
不包含 A 以及 B
未采用 A / B
```

The implementation reuses the existing forbidden-match seam. It requires a
confirmed absence predicate immediately before the first matched target and
allows only recognized coordinate connectors between matched targets. It does
not treat every sentence beginning with `无` or `不` as safe.

## Scope boundaries

The compound scope ends at sentence punctuation, Chinese commas, semicolons,
and adversative or new-clause markers such as `但`, `但是`, `然而`, `不过`,
`而`, and `实际上`. Therefore a denial in one clause cannot suppress a later
positive creation, authority, or membership claim.

## Negative-property protection

`无公开登记的秘密监管机构` remains a positive claim about an existing secret
institution. The predicate is not considered a valid absence predicate because
the target is not immediately after `无`; the intervening property phrase
describes the entity instead of denying its existence. The same protection
applies when that entity is followed by a coordinated target.

## Regression coverage

The offline Live-derived matrix contains 81 cases covering the real Live
sentence, two- and three-item lists, every supported connector, compound
non-use/non-inclusion/adoption, positive controls, negative-property controls,
mixed clauses, and all v0.1.3/v0.1.4 absence and proposal regressions.

## H2 unchanged

`canon_basis.supports` remains a deterministic extractive support contract.
This patch adds no embeddings, semantic similarity, paraphrase resolver, NLP
parser, or LLM judge. Partial or exact-name Canon entity-resolution recall
remains a separate backlog item and is intentionally unchanged.
