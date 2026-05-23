from __future__ import annotations

import argparse
import sys

from app.runner import run_digest


def main() -> None:
    parser = argparse.ArgumentParser(prog="catchup", description="Catch-Up news digest")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Run a digest now")
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
