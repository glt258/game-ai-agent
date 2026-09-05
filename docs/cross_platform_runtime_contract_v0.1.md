# Cross-Platform Runtime Contract v0.1

This document freezes the path and text-encoding rules used by the local
Studio runtime. It does not claim that Windows or macOS execution has passed
remote CI; that verification belongs to W4-S5C and W4-S5E.

## Path categories

- **Repository path**: checkout-relative paths used by Engineering Knowledge,
  Project Graph, development scripts, benchmarks, and evaluation tooling. A
  repository root may be found from Git or repository markers.
- **Runtime resource path**: packaged Canon, Story, knowledge, and reference
  resources below `along_street_resources.data`. Runtime loaders use
  `importlib.resources`; normal Studio requests do not need a checkout.
- **User app-data path**: the stable `game-ai-agent` directory containing the
  default `studio.db`.
- **Temporary/test path**: paths supplied by `tempfile` or pytest `tmp_path`.
  Tests must not write to a real home or platform app-data directory.

Repository paths and user app-data paths are separate contracts. Persistence
does not resolve a repository root and does not require Git.

## App-data and database resolution

`runtime_paths.resolve_database_path()` applies this precedence:

1. An explicit `database_path` argument.
2. `GAME_AI_AGENT_DB_PATH` when it is non-empty.
3. The platform app-data directory plus `studio.db`.

Explicit paths preserve native `Path` semantics. Relative paths are relative to
the current process working directory; `~` and shell-style `$HOME` or
`%USERPROFILE%` expansion are not performed. This keeps explicit user
configuration visible rather than silently changing it.

The resolver is pure and does not create directories. SQLite bootstrap creates
the parent directory when persistence is opened. If that directory cannot be
created or opened, persistence raises a typed configuration error and never
falls back to the current working directory.

The app directory name is always `game-ai-agent`:

| Platform | App-data root | Result |
| --- | --- | --- |
| Windows | non-empty `LOCALAPPDATA`, otherwise `Path.home()/AppData/Local` | `<root>/game-ai-agent/studio.db` |
| Linux/other POSIX | non-empty `XDG_DATA_HOME`, otherwise `Path.home()/.local/share` | `<root>/game-ai-agent/studio.db` |
| macOS | `Path.home()/Library/Application Support` | `<root>/game-ai-agent/studio.db` |

The resolver accepts injected platform, environment, and home values for
portable tests. It does not attempt to identify or reject OneDrive, iCloud,
NFS, SMB, or other synced/network filesystems. Those locations are not
recommended or guaranteed for SQLite persistence; hardening is deferred.

## Repository and Git boundary

Project Graph and Engineering Knowledge are repository-mode development
capabilities. They resolve a repository root from the graph location/Git and
reject machine-local absolute canonical roots. Hybrid evidence identity may
also use Git. The installed Studio runtime, packaged resources, SQLite
bootstrap, Character Save/Open, and runtime loaders do not depend on Git or
Project Graph.

The live benchmark is a repository-only tool. Its `ROOT` value anchors imports,
while its `Path.cwd()` repository argument is an intentional execution-root
precondition for the Git-backed evidence identity; it is not used by runtime
persistence. Its output location remains an explicit CLI argument/default
owned by the benchmark and is not a runtime app-data path.

## UTF-8 and subprocess text

All project-controlled YAML, JSON, Markdown, fixtures, and runtime resource
text are UTF-8. Text file reads and writes specify `encoding="utf-8"` (with
`utf-8-sig` only where an existing input contract explicitly permits a BOM).
JSON canonicalization and `ensure_ascii=False` behavior are unchanged.

Git and other project-controlled subprocess text capture specifies UTF-8 and
strict decoding. A decoding failure is surfaced; `errors="ignore"` is not
allowed for output used to resolve or compare paths. Binary subprocess output
remains bytes and is decoded only at an explicit boundary.

Chinese path names and content are supported by the contract and covered by
focused tests. URL values such as `BACKEND_API_URL` remain URLs and are never
passed through filesystem path resolution; its localhost fallback is
platform-independent.

Acceptance diagnostics preserve the real Unicode commands, paths, and child
logs. When the current stdout or stderr encoding cannot represent a value,
only its display form uses deterministic backslash escapes; execution and
filesystem semantics remain unchanged.

## Frontend runtime

The frontend continues to use npm and `web/package-lock.json` with `npm ci`.
`web/package.json` declares Node `>=20.9.0`; Node 22.x is the recommended
development/CI line. `BACKEND_API_URL` remains a server-side URL rewrite
setting and defaults to `http://127.0.0.1:8000`.

## Persistence boundary

This contract does not change domain semantics, Character/Skill/Binding/
Association/CharacterKit/Report behavior, or the SQLite schema. Schema v4,
foreign keys, the five-second busy timeout, `BEGIN IMMEDIATE`, and SQLite's
default journal mode remain unchanged. The DB is one local SQLite store; WAL,
network-filesystem hardening, and synced-folder support are deferred.
