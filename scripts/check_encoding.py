#!/usr/bin/env python3
"""
Scan text source files for two corruption signatures that have repeatedly
hit this project:

1. UTF-8 BOM (\\xef\\xbb\\xbf) anywhere in the file.
2. Unicode Private Use Area characters (U+E000-U+F8FF). Legitimate Chinese
   text never uses this range, so any occurrence is a reliable sign that a
   tool mis-decoded/re-encoded the file at some point (mojibake).

Usage:
    python scripts/check_encoding.py            # scan the whole repo
    python scripts/check_encoding.py --staged    # scan only git-staged files
                                                  # (used by the pre-commit hook)

Exit code is 1 if any offender is found, 0 otherwise.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCAN_EXTENSIONS = {
    ".py", ".vue", ".js", ".ts", ".jsx", ".tsx", ".json",
    ".md", ".css", ".scss", ".html", ".yml", ".yaml",
}

EXCLUDE_DIR_NAMES = {
    "node_modules", ".venv", "venv", "dist", "build", "unpackage",
    ".git", "__pycache__", "logo", "outputs",
}

BOM = b"\xef\xbb\xbf"
PUA_LOW, PUA_HIGH = 0xE000, 0xF8FF


def iter_repo_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_EXTENSIONS:
            continue
        if any(part in EXCLUDE_DIR_NAMES for part in path.parts):
            continue
        yield path


def iter_staged_files():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    for rel in result.stdout.splitlines():
        path = ROOT / rel
        if path.is_file() and path.suffix.lower() in SCAN_EXTENSIONS:
            yield path


def find_pua_chars(text: str) -> list[str]:
    seen = []
    for ch in text:
        cp = ord(ch)
        if PUA_LOW <= cp <= PUA_HIGH and ch not in seen:
            seen.append(ch)
    return seen


def check_file(path: Path) -> list[str]:
    problems = []
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [f"could not read: {exc}"]

    if BOM in raw:
        count = raw.count(BOM)
        problems.append(f"contains UTF-8 BOM ({count}x)")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        problems.append(f"not valid UTF-8: {exc}")
        return problems

    pua = find_pua_chars(text)
    if pua:
        codepoints = ", ".join(f"U+{ord(c):04X}" for c in pua[:10])
        more = f" (+{len(pua) - 10} more)" if len(pua) > 10 else ""
        problems.append(f"contains {len(pua)} private-use-area char(s): {codepoints}{more}")

    return problems


def main():
    staged_only = "--staged" in sys.argv
    files = list(iter_staged_files() if staged_only else iter_repo_files())

    offenders = []
    for path in files:
        problems = check_file(path)
        if problems:
            offenders.append((path.relative_to(ROOT), problems))

    if not offenders:
        scope = "staged files" if staged_only else f"{len(files)} scanned files"
        print(f"OK: no BOM / mojibake signatures found in {scope}.")
        return 0

    print(f"Found encoding problems in {len(offenders)} file(s):\n")
    for rel_path, problems in sorted(offenders, key=lambda x: str(x[0])):
        print(f"  {rel_path}")
        for p in problems:
            print(f"    - {p}")
    print(f"\n{len(offenders)} file(s) with encoding problems.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
