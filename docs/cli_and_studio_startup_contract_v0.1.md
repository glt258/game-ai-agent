# CLI and Studio Startup Contract v0.1

## Commands and exit codes

The installable entry point is `game-ai-agent`. It uses standard-library
`argparse` and retains `along-street-character-author` unchanged.

```text
game-ai-agent --help
game-ai-agent doctor [--json]
game-ai-agent studio [--backend-host HOST] [--backend-port PORT]
                       [--frontend-host HOST] [--frontend-port PORT]
                       [--db-path PATH] [--no-browser]
```

Exit `0` means success or usable runtime, `1` means an environment/runtime
blocker, and `2` means invalid CLI usage. Doctor check statuses are `pass`,
`warn`, `fail`, and `info`; aggregate states are `ready`,
`ready_with_warnings`, and `blocked`. JSON has stable `status`, `core_ready`,
`studio_ready`, and `checks` fields.

## Doctor boundary

Doctor checks Python (>=3.10), package imports and resources, temporary SQLite
capability, the resolved database path and writability, FastAPI, Node
(minimum 20.9.0; 22.x recommended), npm, frontend presence/build, optional
Git/Project Graph tooling, provider configuration presence, and Studio ports.
It never migrates a user database, calls a provider, installs dependencies, or
downloads anything. Provider output is only `configured` or `not configured`;
credentials are never printed.

An installed wheel supports the core runtime and reports Studio as unavailable
outside a checkout. Missing frontend assets therefore do not block core
Doctor. Git is optional for installed core runtime and informative in a
source checkout.

## Studio boundary and lifecycle

`studio` requires a full source checkout containing `pyproject.toml`, `src/`,
`web/package.json`, and a prepared `web/.next` production build. It does not
run `npm ci`, `npm install`, or other network preparation. Defaults are loopback
(`127.0.0.1:8000` for FastAPI and `127.0.0.1:3000` for Next.js); occupied
ports fail before either child starts.

The launcher uses the current `sys.executable -m uvicorn` and PATH-resolved
`npm`/`npm.cmd` with `npm run start`, passes `BACKEND_API_URL`, preserves an
explicit `GAME_AI_AGENT_DB_PATH`, polls backend health for 30 seconds and the
frontend for 60 seconds, then opens the frontend with `webbrowser.open` unless
`--no-browser` is supplied. Child output is inherited. Ctrl+C, startup failure,
or unexpected child exit performs bounded sibling cleanup. POSIX uses process
groups/signals; Windows uses a new process group and `CTRL_BREAK_EVENT`, with a
termination fallback. Normal shutdown never uses `taskkill`.

Argument arrays with `shell=False` preserve paths containing spaces or Unicode.
SQLite bootstrap/schema v4 remain backend responsibilities and the existing
`runtime_paths` resolver remains the path authority. This CLI adds no domain,
Skill, CharacterKit, provider, or persistence semantics.

## Known limitations

There is no standalone desktop executable, automatic Node/npm installation,
cloud sync, autosave, or production live-provider flow in v0.1. Final fresh
clone verification across Windows, Linux, and macOS is a later S5E activity.
