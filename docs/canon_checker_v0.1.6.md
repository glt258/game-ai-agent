# Canon Checker v0.1.6 — Unified Compound Absence Resolution

## Hermes v0.6.5 blocker

Hermes found that:

```text
无秘密政府机构或秘密行政机构要素
```

could be accepted through the generic forbidden-pattern matcher but rejected
through the literal request-forbidden matcher. The clause has one absence
predicate covering two coordinated targets, so both targets must be negative.

## Root cause

Compound absence was resolved using a matcher-local `current_target_index`.
The generic regex saw both targets and could identify the second coordinate
item. A literal forbidden term saw only its own match, so the same target was
treated as the first item and lost the clause-level absence scope. Polarity was
therefore dependent on which regex happened to find the target.

## Unified resolution

Forbidden matching now follows this deterministic flow:

```text
clause
  -> collect relevant forbidden target spans
  -> normalize and deduplicate exact/overlapping spans
  -> identify the coordinate chain
  -> resolve shared target-level polarity
  -> let the specific detector consume that polarity
```

Target collection reuses the existing literal, generic, and secret
administrative forbidden patterns. Candidate spans containing a connector or
clause boundary are discarded, and overlapping hits prefer the longer span so
literal and generic hits cannot create duplicate coordinate items.

The existing connectors remain supported: `或`, `或者`, `与`, `和`, `及`, `以及`,
`、`, and `/`. Absence and non-use scope remains bounded by sentence
punctuation, Chinese commas, and the existing adversative/new-clause markers.

## Path consistency invariant

For the same clause and target span, literal and generic forbidden matching now
consume the same clause-level polarity. This applies to both negative compound
claims, which are allowed, and positive compound claims, which remain blocked.

## Regression coverage

The offline Live-derived matrix contains 91 cases with:

- the four Hermes exact strings, all `SAFE`;
- literal and generic negative-path consistency;
- literal and generic positive controls;
- two- and three-target coordinate chains;
- mixed-clause boundary protection; and
- negative-property protection.

The four exact Hermes strings are:

```text
无秘密政府机构或秘密行政机构要素
未使用秘密政府组织或秘密行政机构
未采用秘密监管机构与秘密政府组织作为背景
不涉及秘密政府机构或秘密行政机构
```

All four are accepted as negative claims. Positive claims such as
`存在秘密政府机构或秘密行政机构` remain hard failures.

## Protection rules unchanged

`无公开登记的秘密监管机构` remains a positive claim about an existing entity,
not an absence of the entity, and therefore remains blocked. A negative clause
also cannot suppress a later positive clause after the existing boundary
markers.

Action-denial polarity, single-target absence, and existing hard-constraint,
world-rule, and forbidden-pattern behavior remain unchanged outside this
shared compound target resolution.

## H2 and backlog unchanged

`canon_basis.supports` remains a deterministic extractive support contract.
This patch adds no embeddings, semantic similarity, paraphrase resolver, NLP
parser, or LLM judge. Partial or exact-name Canon entity-resolution recall
remains a separate backlog item and is intentionally unchanged.
