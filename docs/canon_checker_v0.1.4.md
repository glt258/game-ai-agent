# Canon Checker v0.1.4 — Absence Negation & Proposal Ordering Hardening

## Hermes v0.6.3 re-acceptance findings

The remaining deterministic gaps were narrow and Live-derived:

- absence or non-use of a forbidden concept was treated as presence;
- a generic `为新增设计` marker could be evaluated before the proposal's
  relation or assignment head.

This patch remains offline-only and changes only the read-only `CanonChecker`
validation contract.

## Absence and non-use denial

The checker now distinguishes a local absence predicate from a negative
property attached to an existing entity. These forms are safe when applied to
the forbidden concept itself:

```text
无秘密政府组织元素
未使用任何秘密政府组织
不包含秘密监管机构
未采用秘密行政机关作为角色背景
不涉及秘密政府监管体系
没有秘密监管机构相关设定
```

The predicate is restricted to known absence and non-use forms immediately
before the matched forbidden concept. A sentence-wide `无` or `不` does not
make a claim safe. For example, `无公开登记的秘密监管机构` still describes
an existing secret institution and remains a positive forbidden claim. Mixed
clauses are evaluated locally, so a later positive secret entity cannot be
hidden by an earlier denial.

Positive controls remain blocked, including secret-government organizations,
secret regulatory institutions used for centralized control, undisclosed
administrative backgrounds, and equivalent secrecy-marker variants.

## Proposal-head ordering

Existing Canon targets are classified in this order:

1. identify the existing target and the proposal head;
2. allow relation, interaction, membership, or assignment-to-target usage;
3. classify an existing entity itself as a new entity and fail closed;
4. apply explicit entity-introduction markers to the remaining ambiguous form.

Therefore these are allowed as proposed content:

```text
与余弦的关系为新增设计
与纪衡的一次工作交接为新增设计
与唐栖的短暂接触为拟议设计
在回写与社会认知组中的资料整理任务为新增设计
```

These remain blocked:

```text
余弦为新增角色设计
新增角色：余弦
回写与社会认知组为新增部门设计
南栈演出散场事故为新事件设计
```

`PROPOSAL_PRESENTED_AS_CANON` continues to be checked separately when a
relation proposal is later narrated as established Canon.

## Regression and limitation boundary

The offline Live-derived suite contains 59 cases covering the absence
predicates, positive controls, mixed clauses, natural interactions, proposal
ordering, existing divisions, and H1 protections. The H2
`canon_basis.supports` contract is unchanged: support remains deterministic
and extractive, with no embeddings, semantic paraphrase resolver, or LLM
judge.
