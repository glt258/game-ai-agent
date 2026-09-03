# Cross-Platform CI Contract v0.1

S5C makes portability a required main-branch CI signal. Ubuntu keeps the full
Python suite on 3.10, 3.13, and 3.14. A dedicated Python 3.13 platform smoke
runs on Ubuntu, Windows, and macOS and exercises native runtime paths, a
Unicode temporary SQLite database, schema v4, Character save/open across a
connection boundary, a Skill/Binding/Association/CharacterKit round trip, and
FastAPI health/OpenAPI startup.

`ekl-portability` runs the fast graph, preflight, and postflight portability
checks on Ubuntu 3.13. It is separate from the full suite so failures identify
Engineering Knowledge path or graph problems quickly.

The `frontend` job runs `npm ci`, unit tests, typecheck, lint, and build on
Ubuntu with Node 22. `frontend-platform-smoke` runs install and build on
Windows and macOS. `browser-e2e` runs one offline Chromium flow on Ubuntu:
generate, edit/validate, attach a Skill, save, open from Saved Characters,
verify the Kit, and re-save. It makes no live provider calls.

The built pure-Python wheel is downloaded by an installed-smoke matrix on all
three operating systems. Each job runs outside the checkout and checks imports,
packaged resources, the offline CLI, Unicode SQLite persistence, and runtime
path overrides. `ci-success` fails closed if any required job is failed,
cancelled, or skipped.

This contract does not claim end-user distribution packaging, Apple Silicon
coverage beyond the architecture printed by the macOS runner, multiple
browsers, or full Python/frontend suites on every operating system.
