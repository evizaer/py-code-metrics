"""CLI entry point for py-code-metrics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from py_code_metrics.analyze import analyze_path
from py_code_metrics.analyze_tests import analyze_tests_path
from py_code_metrics.report import report_to_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="py-code-metrics",
        description=(
            "Compute anti-spaghetti structural metrics, or static test-quality "
            "(oracle/smell) metrics with --tests."
        ),
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Directory (or single .py file) to analyze recursively",
    )
    parser.add_argument(
        "--tests",
        action="store_true",
        help="Analyze test modules for oracle strength and fake-test smells (P0)",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation (default: 2)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    path: Path = args.path
    if not path.exists():
        print(f"error: path does not exist: {path}", file=sys.stderr)
        return 2
    report = analyze_tests_path(path) if args.tests else analyze_path(path)
    sys.stdout.write(report_to_json(report, indent=args.indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
