from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run_pipeline


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Run the reproducible Ampoule publication analysis"
    )
    command.add_argument("--input", required=True, type=Path, help="Snapshot directory")
    command.add_argument("--output", required=True, type=Path, help="New output directory")
    command.add_argument("--config", type=Path, help="Analysis TOML configuration")
    command.add_argument(
        "--legacy-pilot",
        action="store_true",
        help="Allow an exploratory protocol-1 snapshot; never pools protocol versions",
    )
    command.add_argument(
        "--strict",
        action="store_true",
        help="Fail if a required statistical model cannot be fitted",
    )
    return command


def main() -> None:
    args = parser().parse_args()
    output = run_pipeline(
        args.input,
        args.output,
        config_path=args.config,
        legacy_pilot=args.legacy_pilot,
        strict=args.strict,
    )
    print(f"Analysis written to {output}")


if __name__ == "__main__":
    main()
