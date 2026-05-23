from __future__ import annotations

import argparse

from app.runner import run_digest


def main() -> None:
    parser = argparse.ArgumentParser(prog="catchup", description="Catch-Up news digest")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Run a digest now")
    args = parser.parse_args()

    if args.command == "run":
        run = run_digest()
        print(
            f"Run {run.run_id}: status={run.status.value} "
            f"collected={run.collected} new={run.new} -> {run.outputs.get('md')}"
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
