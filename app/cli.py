from __future__ import annotations

import argparse
import sys

from app.runner import run_digest


def main() -> None:
    parser = argparse.ArgumentParser(prog="catchup", description="Catch-Up news digest")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Run a digest now")
    serve_p = sub.add_parser("serve", help="Run the API server")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.command == "run":
        try:
            run = run_digest()
            print(
                f"Run {run.run_id}: status={run.status.value} "
                f"collected={run.collected} new={run.new} -> {run.outputs.get('md')}"
            )
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "serve":
        import uvicorn

        from app.api.app import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
