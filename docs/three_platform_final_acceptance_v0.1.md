# Three-Platform Final Acceptance v0.1

W4-S5E is the release acceptance boundary for the existing Web v0.1 Studio. It adds no product semantics, persistence features, or schema changes.

## Scope and matrix

The required matrix is `ubuntu-latest`, `windows-latest`, and `macos-latest`, each on canonical Python 3.13 and Node 22. Each child starts with `actions/checkout`, installs the package non-editably, runs from the source checkout, and owns its own temporary files. Existing Python 3.10/3.13/3.14, platform smoke, frontend, browser, packaging, and startup gates remain separate.

The package/core boundary is the installed Python package plus the source-checkout `web/` frontend. The acceptance job does not reuse a virtualenv, `.next` directory, SQLite database, or artifact from another job.

## Formal flow

`final_platform_acceptance.py` runs `game-ai-agent --help` and `--version`, then `doctor` and `doctor --json` before the frontend build. Before the build, core readiness is required and `studio_ready=false` is allowed. It performs `npm ci` and `npm run build`, then requires human and JSON doctor output with `core_ready=true`, `studio_ready=true`, and a non-blocked result.

It starts the real `game-ai-agent studio --no-browser` twice on `127.0.0.1` with dynamic ports and a fresh Unicode temporary `GAME_AI_AGENT_DB_PATH`. Each run requires the backend `/api/system/health` HTTP 200 response, frontend HTTP readiness, and a live launcher. Run 1 uses the formal FastAPI save flow to persist a Character, Skill association, and CharacterKit. After graceful bounded shutdown, Run 2 uses the same database and verifies Character ID, current revision, Character payload, association identity, and CharacterKit assignment/digest.

After each shutdown the helper verifies the launcher exit code, rebinds both ports, and reopens SQLite through `PersistenceUnitOfWork`, requiring schema v4. Force-kill fallback is reported as failure. Logs are runner-temporary and failure output includes stage, platform, command, exit code, and inherited launcher output labelled for backend/frontend diagnostics; provider secrets are removed and fake-secret output is redaction-checked.

## Browser boundary and exclusions

Three-platform Playwright is not required. The existing Ubuntu Chromium E2E remains the browser-level proof for Character → Skill → Attach → CharacterKit → Save/Open → Reload. S5E verifies the same persistence contract through the formal HTTP adapter on all three operating systems.

This acceptance does not add live provider calls, Electron/Tauri, desktop packaging, automatic Node/npm installation, cloud deployment, multi-agent behavior, new Character/Skill/Kit semantics, or schema v5. It must not write to platform application-data defaults; all acceptance state is under runner temporary storage.

## Apple Silicon boundary

The macOS job records `platform.machine()`. Apple Silicon is `VERIFIED` only when the hosted runner reports `arm64`; otherwise it remains `UNVERIFIED`. No architecture claim is inferred from the operating-system label.

Local candidate success is `W4_S5E_READY`, not remote closeout. W4-S5E is remotely closed only after the exact candidate passes all three hosted final-acceptance jobs and the existing required `ci-success` chain.
