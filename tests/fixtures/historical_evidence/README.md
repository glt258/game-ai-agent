# Historical evidence fixtures

This directory is a committed, test-only fixture namespace. It contains a
selected set of sanitized evidence metadata copied from local historical runs
so tests remain reproducible in a clean checkout where the ignored
`evals/results` directory is absent.

The fixtures intentionally contain no raw prompts, raw responses, candidates,
IR payloads, credentials, or other secrets. They preserve only the metadata
needed by validator, identity, cohort, and historical-integrity tests.

Production runners continue to read and write `evals/results` by default.
These fixtures do not replace production evidence and do not authorize live
provider calls.
