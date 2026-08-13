# Knowledge Resolver v0.2

## Purpose

`KnowledgeResolver` answers one narrow question: whether a character is allowed to access a Lore record in the current runtime context. It does not retrieve Lore content and does not model belief, confidence, rumor belief, or opinions.

## Data flow

```text
Character identity + Knowledge Rules + Lore metadata + explicit runtime context
                                |
                                v
                       KnowledgeResolver
                                |
                 allow/deny + explainability trace
                                |
                       Lore Retriever / Agent
```

Characters, factions, Lore, and knowledge rules remain the source of truth. The resolver does not write permissions back into Character Canon and does not create `known_lore`, `known_secrets`, or `knowledge_level` fields.

## Default deny and public access

`sensitivity: public` is allowed through the configured public policy and returns `reason_code: public_lore`. Non-public Lore requires a fully matching rule. No relationship, gameplay rarity, phenotype, occupation string, agent profile, or faction membership can substitute for a matching rule.

## Subject matching

The resolver reads the vocabulary from `data/knowledge/knowledge_rules.yaml`. Supported subjects in the current policy are `everyone`, `faction`, `division`, `role`, `responsibility`, `assignment`, and `explicit_grant`.

Static subjects are matched only against `character.identity`. A subject carrying `faction_id` also requires the character's exact faction to match. Role, responsibility, and assignment names are not inferred from occupation or tags.

## Condition Scope Binding v0.2

Conditions are bound by `data/knowledge/condition_scopes.yaml` using the key
`rule_id + condition`. The registry defines whether the scope is `resolved` or
`unresolved`, the scope type, match mode, and concrete Canon IDs. Missing
bindings and unresolved bindings fail closed with distinct reason codes.

The registry has no authority to allow access by itself. A successful decision
still requires subject matching, a resolved scope binding, and runtime IDs that
match that binding.

## Project Registry and Authorization Registry

`data/projects/projects.yaml` defines canonical project identities. It contains
only projects supported by explicit Canon evidence, with references to their
faction, Lore, and registered assignments. Research themes or similar Lore do
not by themselves establish a Project identity.

`data/knowledge/authorizations.yaml` defines concrete authorization keys and
their specific targets. It does not record current holders and is not an ACL.

Neither registry independently grants Lore access. A project or authorization
must be referenced by a resolved binding in `condition_scopes.yaml`, and the
subject plus concrete runtime context must still match.

## Scope integrity

Resolved binding values must reference registered machine-readable vocabulary
or a canonical external registry. Bindings for project, case, incident,
authorization, artist-team, or role-assignment scopes remain unresolved until
their registries and concrete targets exist. Unresolved bindings have empty values and an explicit
`unresolved_reason`; they fail closed.

## Runtime context and evaluators

`KnowledgeContext` contains only explicit runtime IDs:

- `active_responsibilities`, `active_assignments`, `active_projects`
- `active_cases`, `active_incidents`, `authorizations`
- `active_roles`, `artist_teams`

The condition name and evaluator name are separate. The mapping is read from
the rule vocabulary, while the registry supplies the required scope. Boolean
permission fields such as `allow`, `related`, or `assignment_match` are not
accepted as runtime context.

The Project/StoryState boundary may tell the resolver that a character is
currently active in `project_x`; the Authorization/StoryState boundary may tell
it that a character currently holds `auth_x`. Neither upstream system can tell
the resolver that the character can access `lore_x`; that decision remains
resolver-owned.

## Decision trace

Every non-public candidate grant records its rule id, required and actual subject data, condition results, final outcome, and a reason code. The trace never includes the Lore statement or other private Lore content.

`KnowledgeDecision.to_dict()` is suitable for CLI and eval output. `require_access()` raises `KnowledgeAccessDenied` only for a valid query whose decision is deny; unknown identifiers raise `UnknownCharacterError` or `UnknownLoreError` instead.

## Known limitation

Some current Canon conditions remain explicitly `unresolved` because no
canonical project, case, incident, dataset, review, or artist-team ID
registry/target exists yet. This is reported as a scope gap rather than filled with guessed
placeholder IDs. Titles, descriptions, faction names, LLM similarity,
embeddings, RAG, network calls, and randomness are intentionally not used.

## Eval strategy

Run:

```text
python -m pytest -q
python scripts/validate_data.py
python scripts/validate_knowledge_scopes.py
python scripts/run_knowledge_evals.py
python scripts/report_knowledge_scopes.py
python scripts/report_knowledge_scope_gaps.py
```

The eval dataset covers public access, default denial, faction-not-full-access, missing dynamic context, secret denial, and invalid query errors. Positive conditional access is covered by synthetic in-memory unit fixtures so Canon files are not changed merely to manufacture privileged playable characters.

## Future work

- Add canonical Case, Incident, Artist Team, and Role-assignment registries.
- Add Dataset or Review registries only if Canon evidence establishes that they
  are needed by currently unresolved conditions.
- Design new responsibility vocabulary in a separate Knowledge Responsibility
  Vocabulary task; Support Registries must not create responsibility IDs.
- Integrate those registries with StoryState, Quest, and Case System runtime
  context providers.
- Add the independent Belief Layer and Lore Retriever / RAG integration.
