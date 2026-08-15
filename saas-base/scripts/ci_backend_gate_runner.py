#!/usr/bin/env python3
"""CI-only helper for Backend Candidate Certification (TEST-INFRA-02).

stdlib only -- no third-party imports. Never executes any test/business
logic itself: it only validates a list of candidate test file paths and
invokes pytest via subprocess with a real argv list (never shell=True, never
string concatenation into a shell command, never eval/exec, never a dynamic
import of business code). This keeps the workflow YAML free of inline path
validation/injection-prone shell logic for both Gate A (paths come from
`git diff` output) and Gate B (paths come from the checked-in manifest).

Usage:
    python ci_backend_gate_runner.py --repo-root <path> --paths-file <path> validate
    python ci_backend_gate_runner.py --repo-root <path> --paths-file <path> run
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

# Backend test files only: relative, under tests/, no parent-dir traversal,
# no absolute paths, no shell metacharacters. Deliberately conservative.
_SAFE_TEST_PATH_RE = re.compile(r"^tests/[A-Za-z0-9_./-]+\.py$")


def validate_paths(raw_lines: list[str], *, repo_root: Path) -> list[str]:
    validated: list[str] = []
    for raw in raw_lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ".." in line:
            print(f"REJECTED (parent-directory traversal): {line}", file=sys.stderr)
            sys.exit(1)
        if line.startswith("/") or line.startswith("~"):
            print(f"REJECTED (absolute/home path): {line}", file=sys.stderr)
            sys.exit(1)
        if not _SAFE_TEST_PATH_RE.match(line):
            print(f"REJECTED (does not match ^tests/[A-Za-z0-9_./-]+\\.py$): {line}", file=sys.stderr)
            sys.exit(1)
        full = repo_root / line
        if not full.is_file():
            print(f"REJECTED (does not exist in target checkout): {line}", file=sys.stderr)
            sys.exit(1)
        if line not in validated:
            validated.append(line)
    return validated


def _load_paths(args: argparse.Namespace) -> list[str]:
    repo_root = Path(args.repo_root).resolve()
    raw_lines = Path(args.paths_file).read_text(encoding="utf-8").splitlines()
    return validate_paths(raw_lines, repo_root=repo_root)


def cmd_validate(args: argparse.Namespace) -> None:
    validated = _load_paths(args)
    if not validated:
        print("NO_VALID_PATHS")
        sys.exit(args.empty_exit_code)
    for path in validated:
        print(path)


def cmd_run(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).resolve()
    validated = _load_paths(args)
    if not validated:
        print("NO_VALID_PATHS -- nothing to run")
        sys.exit(args.empty_exit_code)
    argv = [sys.executable, "-m", "pytest", *validated, "-q", "-W", "error::RuntimeWarning"]
    print("RUNNING:", " ".join(argv))
    result = subprocess.run(argv, cwd=str(repo_root))
    sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, help="saas-base checkout root the paths are relative to")
    parser.add_argument("--paths-file", required=True, help="newline-delimited candidate test paths")
    parser.add_argument(
        "--empty-exit-code", type=int, default=1,
        help="exit code when zero valid paths remain (default 1: fail closed)",
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("validate", help="print the validated path list and exit")
    sub.add_parser("run", help="validate, then run pytest against the validated paths")
    args = parser.parse_args()

    if args.mode == "validate":
        cmd_validate(args)
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
