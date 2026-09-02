# Live Web Execution Contract v0.1

W4-S3G keeps offline Skill design synchronous and moves only explicit live Web
execution to a process-local session job. The job is a transport boundary; it
does not change the HybridProvider → Semantic IR → compiler → evaluator →
alignment pipeline or the canonical SkillDesignArtifact transport.

## Timeout chain audit

| Layer | Budget | Ownership and failure behavior |
| --- | --- | --- |
| Browser fetch | No implicit application timeout | The live POST is short and returns `202`; polling is bounded by the UI. An AbortController cancels polling for a superseded run. |
| Next rewrite | No project-configured timeout | `/api/:path*` is only a rewrite to FastAPI. The previous long-held request ended as a proxy socket reset before FastAPI returned. |
| FastAPI live job POST | Short request only | Validates the live mode and enqueues work; it does not hold the provider request open. |
| Live job registry | 90 seconds by default | Process-local bounded deadline; timeout becomes `BACKEND_REQUEST_TIMEOUT` (`504`). Finished jobs are removed after TTL. |
| Character/Skill application | Normal synchronous pipeline inside the job | Provider, IR, compiler, evaluator, and alignment failures remain distinct safe results/errors. |
| Hybrid provider | 60 seconds by default for the Web seam | The same raw-provider budget as the W4-S3F benchmark; transport retry default is `0`. Overrides are `NPC_LLM_TIMEOUT_SECONDS` and `NPC_LLM_MAX_RETRIES`. |
| OpenAI-compatible client | Provider timeout propagated to SDK request | SDK retries remain disabled; normalized failures include timeout, rate limit, authentication, and connection failure. |
| Remote provider | Governed by the client timeout | The remote service is not treated as an unbounded wait. |

The original synchronous smoke was run with an explicit `60s/0 retry` provider
configuration. Character Studio reached FastAPI, but the long-held Next
connection ended with `socket hang up` while FastAPI remained healthy. This
identifies the failing layer as the long Web/proxy connection lifecycle, not a
FastAPI process crash. The benchmark path was also using `60s/0 retry`, while
the Web environment seam previously fell back to `30s/2 retry`; the Web seam
now defaults to the benchmark baseline.

## Execution decision

```text
SESSION_ASYNC_JOB
```

The synchronous alternative was attempted first and rejected because a
bounded, correctly configured 60-second request still lost its proxy/browser
connection. The asynchronous contract is deliberately small:

- `POST /api/skills/playground/jobs`
- `GET /api/skills/playground/jobs/{job_id}`
- `POST /api/characters/skill-design/jobs`
- `GET /api/characters/skill-design/jobs/{job_id}`

The POST returns an opaque job ID and `PENDING`/`RUNNING`. Poll responses use
`PENDING`, `RUNNING`, `SUCCEEDED`, or `FAILED`. A successful job stores the
normal `web-skill-playground/0.1` or `web-character-skill-design/0.1` response;
there is no second Skill result contract.

## Safety and lifecycle

The registry is in-memory and process-local. Restarting the server loses jobs;
there is no database, queue, recovery, or durable history. Finished jobs have
a bounded TTL, and a small in-flight limit prevents unbounded provider work.
The deadline marks a job failed safely; if a transport thread returns later,
its result is discarded and cannot replace the timeout state.

The browser shows provider alias, model alias, queue/running state, and elapsed
time. It never shows a fake completion percentage or provider credential. A
new run aborts the old polling request and increments a local generation guard;
late results cannot overwrite the current Character context. A live result is
only displayed for review and is never auto-attached to a Character or Kit.

Provider errors are classified as `PROVIDER_TIMEOUT`,
`PROVIDER_CONNECTION_FAILURE`, `PROVIDER_RATE_LIMITED`, or a safe live
execution failure. IR validation and later business-stage failures remain in
the normal result pipeline rather than being converted into provider errors.

## Offline/live separation

Offline fixtures continue to use the existing fast synchronous `/run` and
`/skill-design` endpoints. Only requests that explicitly select
`execution_mode=live` may enter the job endpoints. Unit tests use delayed or
failing injected providers and make no live network calls.
