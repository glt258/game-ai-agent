# Reference Corpus Ingestion Policy v0.2

- Every fact, including every mechanic relation, must be traceable to one or more
  source IDs in `sources.yaml`.
- Unknown facts stay `null` or `[]`; do not guess to improve completeness.
- If a source clearly supports a node-to-node relationship, record it as a
  `MechanicRelation` instead of hiding it in `description_summary`.
- Mechanic relations are facts, not analysis. Claims about role, dependency,
  optimal rotation, or playstyle belong in `analysis.yaml`.
- `PrimaryLoop` describes the observed mechanic flow; it is not an optimal rotation.
- Official-hosted does not automatically mean primary; evaluate who produced the
  content and what it establishes.

The existing v0.1 source and corpus-boundary policies continue to apply. Facts stay
outside Canon and this phase does not add crawler, RAG, PatternExtractor, or agent
integration work.
