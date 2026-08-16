# Reference Corpus Ingestion Policy v0.2

- Every fact, including every mechanic relation, must be traceable to one or more
  source IDs in `sources.yaml`.
- Unknown facts stay `null` or `[]`; do not guess to improve completeness.
- If a source clearly supports a node-to-node relationship, record it as a
  `MechanicRelation` instead of hiding it in `description_summary`.
- Mechanic relations are facts, not analysis. Claims about role, dependency,
  optimal rotation, or playstyle belong in `analysis.yaml`.
- `StateFact.subject_scope` records the subject that carries or is affected by a
  state; it is not the entity that created or applied the state.
- Do not infer state scope from who applies the state. When a character applies
  a status to an enemy, use `target`; when evidence does not establish the
  subject, use `unknown`.
- The provisional state subject vocabulary is `self`, `target`, and `unknown`.
  Do not add broader taxonomy values without a Golden Record review.
- `PrimaryLoop` describes the observed mechanic flow; it is not an optimal rotation.
- Official-hosted does not automatically mean primary; evaluate who produced the
  content and what it establishes.

The existing v0.1 source and corpus-boundary policies continue to apply. Facts stay
outside Canon and this phase does not add crawler, RAG, PatternExtractor, or agent
integration work.

Temporal provenance policy:

- `field_evidence` records evidence for the current `CharacterFacts` value, not every historical mention of a field.
- Do not infer `supersedes` solely from a later publication date. Use it only when the later source explicitly changes, replaces, or is incompatible with the earlier current fact.
- Use `clarifies` for official wording clarification that does not change the underlying gameplay behavior.
- `superseded` is not `conflicted`, and a clarified source does not automatically invalidate the source it clarifies.
- Historical official sources may remain in `sources` and `source_relations`, but a source superseded for a field must not remain in current `field_evidence` for that field.
