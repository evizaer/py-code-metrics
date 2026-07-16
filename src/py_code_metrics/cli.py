"""CLI entry point for py-code-metrics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from py_code_metrics.analyze import analyze_path
from py_code_metrics.analyze_tests import analyze_tests_path
from py_code_metrics.compare import compare, load_report
from py_code_metrics.install_cmd import (
    InstallError,
    acquire_editable,
    acquire_pip_user,
    acquire_uv_dev,
    format_install_summary,
    run_project_post_install,
    run_user_post_install,
)
from py_code_metrics.metrics.test_delta import changed_python_paths
from py_code_metrics.model import MetricsReport, TestMetricsReport
from py_code_metrics.report import report_to_json
from py_code_metrics.views import (
    board_view,
    dou_view,
    findings_view,
    hotspots_view,
    symbol_view,
)

_TOP_LEVEL_SETUP_FLAGS = frozenset(
    {
        "--install-for-project",
        "--install-for-user",
        "--uv-dev",
        "--pip-user",
        "--editable",
    }
)


def build_subcommand_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="py-code-metrics",
        description="Agent-oriented views and full structural / test analysis.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_diff = sub.add_parser("diff", help="Compare two snapshots; gate regressions")
    p_diff.add_argument("before", type=Path)
    p_diff.add_argument("after", type=Path)
    p_diff.add_argument(
        "--json",
        action="store_true",
        help="Emit compact JSON gate envelope instead of text",
    )
    p_diff.add_argument("--indent", type=int, default=2)
    _add_path_filter_args(p_diff)

    for name, help_text in (
        ("board", "Complementary rollups only"),
        ("hotspots", "Ranked unpaid hotspots"),
        ("dou", "Ranked dict-overuse (structured-mapping) sites"),
        ("analyze", "Full hierarchical JSON report"),
    ):
        p = sub.add_parser(name, help=help_text)
        _add_report_source_args(p)
        if name in {"hotspots", "dou"}:
            p.add_argument("--limit", type=int, default=None)
            _add_path_filter_args(p)

    p_sym = sub.add_parser("symbol", help="Single callable or class by qualified name")
    _add_report_source_args(p_sym)
    p_sym.add_argument("qname", help="Qualified name to look up")

    p_snap = sub.add_parser("snapshot", help="Write full report to a file")
    p_snap.add_argument("path", type=Path, help="Directory or file to analyze")
    p_snap.add_argument("-o", "--output", type=Path, required=True, metavar="FILE")
    p_snap.add_argument("--indent", type=int, default=2)
    p_snap.add_argument(
        "--tests",
        action="store_true",
        help="Snapshot test-quality report instead of structural",
    )
    p_snap.add_argument("--coverage", type=Path, default=None, metavar="FILE")
    p_snap.add_argument("--mutation", type=Path, default=None, metavar="FILE")
    p_snap.add_argument(
        "--delta",
        action="store_true",
        help="With --tests: filter findings to git-changed *.py paths",
    )

    p_tests = sub.add_parser("tests", help="Test-quality findings (compact by default)")
    p_tests.add_argument("path", type=Path)
    p_tests.add_argument("--coverage", type=Path, default=None, metavar="FILE")
    p_tests.add_argument("--mutation", type=Path, default=None, metavar="FILE")
    p_tests.add_argument(
        "--delta",
        action="store_true",
        help="Filter findings to git-changed *.py paths",
    )
    p_tests.add_argument(
        "--full",
        action="store_true",
        help="Emit the full hierarchical test report",
    )
    p_tests.add_argument("--limit", type=int, default=None)
    p_tests.add_argument("--indent", type=int, default=2)
    p_tests.add_argument(
        "-f",
        "--from-file",
        type=Path,
        default=None,
        metavar="FILE",
        help="Read an existing test-quality snapshot instead of analyzing",
    )

    return parser


def _add_report_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=None,
        help="Directory or file to analyze (omit when using -f)",
    )
    parser.add_argument(
        "-f",
        "--from-file",
        type=Path,
        default=None,
        metavar="FILE",
        help="Read an existing structural snapshot instead of analyzing",
    )
    parser.add_argument("--indent", type=int, default=2)


def _add_path_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--paths",
        type=Path,
        nargs="*",
        default=None,
        metavar="FILE",
        help="Restrict to these *.py paths (hotspots/dou filter; diff DOU gate scope)",
    )
    parser.add_argument(
        "--delta",
        action="store_true",
        help="Use git-changed *.py paths (hotspots/dou filter; diff DOU gate scope)",
    )


def build_setup_parser() -> argparse.ArgumentParser:
    """Top-level package acquire / project post-install flags (not analyze)."""
    parser = argparse.ArgumentParser(
        prog="py-code-metrics",
        description=(
            "Post-package project setup and optional package acquire helpers. "
            "Not the same as analyzing a path."
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--install-for-project",
        type=Path,
        metavar="ROOT",
        help="Post-install steps for a project (copy Cursor skill into ROOT/.cursor/skills)",
    )
    mode.add_argument(
        "--install-for-user",
        action="store_true",
        help="Copy Cursor skill into ~/.cursor/skills (personal, not committed)",
    )
    mode.add_argument(
        "--uv-dev",
        action="store_true",
        help="Acquire package: uv add --dev py-code-metrics (cwd must be a uv project)",
    )
    mode.add_argument(
        "--pip-user",
        action="store_true",
        help="Acquire package: python -m pip install --user py-code-metrics",
    )
    mode.add_argument(
        "--editable",
        type=Path,
        metavar="PATH",
        help="Acquire package: uv add --dev --editable PATH",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --install-for-*: overwrite divergent skill destination",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --install-for-*: print planned steps without writing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if _is_setup_argv(argv):
        return _main_setup(argv)
    return _main_subcommand(argv)


def _is_setup_argv(argv: list[str]) -> bool:
    return any(a.split("=", 1)[0] in _TOP_LEVEL_SETUP_FLAGS for a in argv)


def _main_setup(argv: list[str]) -> int:
    parser = build_setup_parser()
    args = parser.parse_args(argv)
    try:
        if args.install_for_project is not None:
            results = run_project_post_install(
                args.install_for_project,
                force=args.force,
                dry_run=args.dry_run,
            )
            print(format_install_summary(results, dry_run=args.dry_run))
            return 0
        if args.install_for_user:
            results = run_user_post_install(force=args.force, dry_run=args.dry_run)
            print(format_install_summary(results, dry_run=args.dry_run))
            return 0
        if args.force or args.dry_run:
            print(
                "error: --force and --dry-run apply only to "
                "--install-for-project / --install-for-user",
                file=sys.stderr,
            )
            return 2
        if args.uv_dev:
            return acquire_uv_dev()
        if args.pip_user:
            return acquire_pip_user()
        if args.editable is not None:
            return acquire_editable(args.editable)
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("error: no setup action selected", file=sys.stderr)
    return 2


def _main_subcommand(argv: list[str]) -> int:
    parser = build_subcommand_parser()
    args = parser.parse_args(argv)
    command = args.command
    if command == "diff":
        return _cmd_diff(args)
    if command == "snapshot":
        return _cmd_snapshot(args)
    if command == "tests":
        return _cmd_tests(args)
    if command == "symbol":
        return _cmd_symbol(args)
    if command in {"board", "hotspots", "dou", "analyze"}:
        return _cmd_structural_view(args, command)
    print(f"error: unknown command: {command}", file=sys.stderr)
    return 2


def _cmd_diff(args: argparse.Namespace) -> int:
    try:
        before = load_report(args.before)
        after = load_report(args.after)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 2
    delta_paths = _resolve_diff_delta_paths(args, after)
    code, lines, diff_dict = compare(before, after, delta_paths=delta_paths)
    if args.json:
        sys.stdout.write(json.dumps(diff_dict, indent=args.indent) + "\n")
    else:
        print("\n".join(lines))
    return code


def _resolve_diff_delta_paths(
    args: argparse.Namespace,
    after: MetricsReport,
) -> set[str] | None:
    """Explicit --paths/--delta for DOU gate; None → infer from snapshot fingerprints."""
    explicit = bool(getattr(args, "paths", None)) or bool(getattr(args, "delta", False))
    if not explicit:
        return None
    paths: set[str] = set()
    if args.paths:
        paths.update(str(p).replace("\\", "/") for p in args.paths)
    if args.delta:
        root = _report_root(after, args)
        changed, note = changed_python_paths(root)
        if note and not changed:
            print(f"warning: --delta: {note}", file=sys.stderr)
        paths.update(p.replace("\\", "/") for p in changed)
    return paths


def _cmd_snapshot(args: argparse.Namespace) -> int:
    path: Path = args.path
    if not path.exists():
        print(f"error: path does not exist: {path}", file=sys.stderr)
        return 2
    if args.tests:
        if args.coverage is not None and not args.coverage.exists():
            print(f"error: coverage file does not exist: {args.coverage}", file=sys.stderr)
            return 2
        if args.mutation is not None and not args.mutation.exists():
            print(f"error: mutation file does not exist: {args.mutation}", file=sys.stderr)
            return 2
        try:
            report = analyze_tests_path(
                path,
                coverage_path=args.coverage,
                mutation_path=args.mutation,
                delta=args.delta,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        report = analyze_path(path)
    text = report_to_json(report, indent=args.indent)
    try:
        args.output.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _cmd_tests(args: argparse.Namespace) -> int:
    report, err = _load_or_analyze_tests(args)
    if err is not None:
        print(err, file=sys.stderr)
        return 2
    assert report is not None
    if args.full:
        sys.stdout.write(json.dumps(report.to_dict(), indent=args.indent) + "\n")
        return 0
    view = findings_view(report, limit=args.limit)
    sys.stdout.write(json.dumps(view.to_dict(), indent=args.indent) + "\n")
    return 0


def _cmd_symbol(args: argparse.Namespace) -> int:
    report, err = _load_or_analyze_structural(args)
    if err is not None:
        print(err, file=sys.stderr)
        return 2
    assert report is not None
    view = symbol_view(report, args.qname)
    if view is None:
        print(f"error: symbol not found: {args.qname}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(view.to_dict(), indent=args.indent) + "\n")
    return 0


def _cmd_structural_view(args: argparse.Namespace, command: str) -> int:
    report, err = _load_or_analyze_structural(args)
    if err is not None:
        print(err, file=sys.stderr)
        return 2
    assert report is not None
    if command == "analyze":
        sys.stdout.write(json.dumps(report.to_dict(), indent=args.indent) + "\n")
        return 0
    if command == "board":
        view = board_view(report)
    elif command == "dou":
        path_filter = _resolve_path_filter(args, report)
        view = dou_view(
            report,
            limit=getattr(args, "limit", None),
            path_filter=path_filter,
        )
    else:
        path_filter = _resolve_path_filter(args, report)
        view = hotspots_view(
            report,
            limit=getattr(args, "limit", None),
            path_filter=path_filter,
        )
    sys.stdout.write(json.dumps(view.to_dict(), indent=args.indent) + "\n")
    return 0


def _load_or_analyze_structural(
    args: argparse.Namespace,
) -> tuple[MetricsReport | None, str | None]:
    if args.from_file is not None:
        if not args.from_file.exists():
            return None, f"error: snapshot does not exist: {args.from_file}"
        try:
            return load_report(args.from_file), None
        except (OSError, json.JSONDecodeError) as exc:
            return None, f"error: {exc}"
    if args.path is None:
        return None, "error: path is required unless -f/--from-file is set"
    if not args.path.exists():
        return None, f"error: path does not exist: {args.path}"
    return analyze_path(args.path), None


def _load_test_report(path: Path) -> TestMetricsReport:
    return TestMetricsReport.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _load_or_analyze_tests(
    args: argparse.Namespace,
) -> tuple[TestMetricsReport | None, str | None]:
    if args.from_file is not None:
        if not args.from_file.exists():
            return None, f"error: snapshot does not exist: {args.from_file}"
        try:
            return _load_test_report(args.from_file), None
        except (OSError, json.JSONDecodeError) as exc:
            return None, f"error: {exc}"
    path: Path = args.path
    if not path.exists():
        return None, f"error: path does not exist: {path}"
    if args.coverage is not None and not args.coverage.exists():
        return None, f"error: coverage file does not exist: {args.coverage}"
    mutation = getattr(args, "mutation", None)
    if mutation is not None and not mutation.exists():
        return None, f"error: mutation file does not exist: {mutation}"
    try:
        report = analyze_tests_path(
            path,
            coverage_path=args.coverage,
            mutation_path=mutation,
            delta=args.delta,
        )
    except ValueError as exc:
        return None, f"error: {exc}"
    return report, None


def _resolve_path_filter(args: argparse.Namespace, report: MetricsReport) -> set[str] | None:
    paths: set[str] = set()
    if getattr(args, "paths", None):
        paths.update(str(p).replace("\\", "/") for p in args.paths)
    if getattr(args, "delta", False):
        root = _report_root(report, args)
        changed, note = changed_python_paths(root)
        if note and not changed:
            print(f"warning: --delta: {note}", file=sys.stderr)
        paths.update(p.replace("\\", "/") for p in changed)
    return paths or None


def _report_root(report: MetricsReport, args: argparse.Namespace) -> Path:
    if args.path is not None:
        return args.path.resolve()
    if report.input.root:
        return Path(report.input.root).resolve()
    if args.from_file is not None:
        return args.from_file.resolve().parent
    return Path.cwd()


if __name__ == "__main__":
    raise SystemExit(main())
