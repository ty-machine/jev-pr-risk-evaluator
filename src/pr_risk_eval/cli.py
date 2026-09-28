from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .config import load_config
from .evaluator import evaluate_diff
from .jev import JevError, OpenRouterJevClient, ReplayJevClient
from .report import terminal_report


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="pr-risk",
        description="Triage pull-request risk with deterministic diff facts and TypeSafe Jev.",
    )
    root.add_argument("--version", action="version", version="pr-risk 0.1.0")
    subcommands = root.add_subparsers(dest="command", required=True)
    evaluate = subcommands.add_parser("evaluate", help="evaluate a unified local git diff")
    source = evaluate.add_mutually_exclusive_group()
    source.add_argument("--diff", metavar="PATH", help="read a unified diff from a file; use - for stdin")
    source.add_argument("--staged", action="store_true", help="evaluate git diff --cached")
    source.add_argument("--base", metavar="REF", help="evaluate git diff REF...HEAD")
    evaluate.add_argument("--config", metavar="PATH", help="JSON rubric; defaults to the bundled rubric")
    evaluate.add_argument("--replay", metavar="PATH", help="offline Jev response fixture (no API call)")
    evaluate.add_argument("--title", help="optional PR title included in relevant state")
    evaluate.add_argument("--description", help="optional PR description included in relevant state")
    evaluate.add_argument(
        "--repo",
        metavar="PATH",
        default=".",
        help="Git repository used by --staged or --base (default: current directory)",
    )
    evaluate.add_argument("--json", action="store_true", help="emit stable structured JSON")
    evaluate.add_argument("--timeout", type=float, default=60.0, help="API timeout in seconds (default: 60)")
    return root


def _git_diff(args: list[str], repo: str) -> str:
    check = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    if check.returncode or check.stdout.strip() != "true":
        raise ValueError(
            f"{Path(repo).resolve()} is not a Git repository; use --repo PATH or provide --diff PATH"
        )
    process = subprocess.run(
        ["git", "-C", repo, "diff", "--no-ext-diff", "--no-color", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode:
        message = process.stderr.strip() or "git diff failed"
        raise ValueError(message)
    return process.stdout


def _read_diff(args: argparse.Namespace) -> str:
    if args.diff == "-":
        return sys.stdin.read()
    if args.diff:
        return Path(args.diff).read_text(encoding="utf-8")
    if args.staged:
        return _git_diff(["--cached"], args.repo)
    if args.base:
        return _git_diff([f"{args.base}...HEAD"], args.repo)
    if not sys.stdin.isatty():
        piped = sys.stdin.read()
        if piped.strip():
            return piped
    staged = _git_diff(["--cached"], args.repo)
    return staged if staged.strip() else _git_diff([], args.repo)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = load_config(args.config)
        diff_text = _read_diff(args)
        if not diff_text.strip():
            raise ValueError("the selected diff is empty")
        if args.replay:
            client = ReplayJevClient(args.replay)
        else:
            client = OpenRouterJevClient(os.environ.get("OPENROUTER_API_KEY", ""), timeout=args.timeout)
        result = evaluate_diff(
            diff_text,
            client,
            config,
            title=args.title,
            description=args.description,
        )
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True) if args.json else terminal_report(result))
        return 0
    except (OSError, ValueError, JevError, json.JSONDecodeError) as error:
        print(f"pr-risk: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
