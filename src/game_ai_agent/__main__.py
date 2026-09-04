from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version

from .doctor import main as doctor_main
from .studio import main as studio_main


def _version() -> str:
    try:
        return version("along-street-knowledge-resolver")
    except PackageNotFoundError:
        return "unknown"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="game-ai-agent",
        description="Inspect the Game AI Agent runtime or start the source-checkout Studio.",
    )
    parser.add_argument("--version", action="version", version=_version())
    commands = parser.add_subparsers(dest="command")

    doctor = commands.add_parser("doctor", help="diagnose the local runtime and Studio prerequisites")
    doctor.add_argument("--json", action="store_true", help="emit machine-readable diagnostics")

    studio = commands.add_parser("studio", help="start the source-checkout Studio")
    studio.add_argument("--backend-host", default="127.0.0.1")
    studio.add_argument("--backend-port", type=int, default=8000)
    studio.add_argument("--frontend-host", default="127.0.0.1")
    studio.add_argument("--frontend-port", type=int, default=3000)
    studio.add_argument("--db-path", default=None, help="optional GAME_AI_AGENT_DB_PATH override")
    studio.add_argument("--no-browser", action="store_true", help="do not open a browser after readiness")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor_main(json_output=args.json)
    if args.command == "studio":
        return studio_main(
            backend_host=args.backend_host,
            backend_port=args.backend_port,
            frontend_host=args.frontend_host,
            frontend_port=args.frontend_port,
            db_path=args.db_path,
            no_browser=args.no_browser,
        )
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
