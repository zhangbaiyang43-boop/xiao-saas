#!/usr/bin/env python3
"""One-off deep verification: re-scans a file for CJK tokens (including
mustache-containing template text nodes) and reports any that still have a
clean gb18030 reversal available -- i.e. spots the lighter check_encoding.py
scan can miss. Usage: python scripts/deep_check.py <file> [--apply]
"""
import re
import sys
from pathlib import Path

CJK_LOW, CJK_HIGH = 0x4E00, 0x9FFF
EXT_A_LOW, EXT_A_HIGH = 0x3400, 0x4DBF
PUA_LOW, PUA_HIGH = 0xE000, 0xF8FF
RARE_HIGH = 0x9FA6


def has_cjk(s):
    return any(CJK_LOW <= ord(c) <= CJK_HIGH for c in s)


def is_suspicious(s):
    for c in s:
        cp = ord(c)
        if PUA_LOW <= cp <= PUA_HIGH:
            return True
        if CJK_LOW <= cp <= CJK_HIGH and cp >= RARE_HIGH:
            return True
        if EXT_A_LOW <= cp <= EXT_A_HIGH:
            return True
    return False


token_re = re.compile(
    r'"(?:[^"\\]|\\.)*"'
    r'|\'(?:[^\'\\]|\\.)*\''
    r'|>[^<>\n]+<'
    r'|#[^\n]*'
    r'|//[^\n]*',
    re.DOTALL,
)


def find_reversible(text):
    candidates = []
    for m in token_re.finditer(text):
        tok = m.group()
        s, e = m.start(), m.end()
        if tok.startswith('>') and tok.endswith('<'):
            inner = tok[1:-1]
            if not inner.strip() or not has_cjk(inner):
                continue
            candidates.append((s + 1, e - 1, inner))
        elif has_cjk(tok):
            candidates.append((s, e, tok))

    reversible = []
    for s, e, tok in candidates:
        try:
            recovered = tok.encode("gb18030").decode("utf-8")
        except Exception:
            continue
        if recovered == tok:
            continue
        if has_cjk(recovered) and not is_suspicious(recovered):
            reversible.append((s, e, tok, recovered))
    return reversible


def main():
    path = Path(sys.argv[1])
    apply = "--apply" in sys.argv
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    reversible = find_reversible(text)
    print(f"{path}: {len(reversible)} additional reversible token(s) found")
    for s, e, tok, recovered in reversible:
        line_no = text.count("\n", 0, s) + 1
        print(f"  line {line_no}: {tok!r} -> {recovered!r}")
    if apply and reversible:
        for s, e, tok, recovered in reversed(reversible):
            assert text[s:e] == tok
            text = text[:s] + recovered + text[e:]
        path.write_bytes(text.encode("utf-8"))
        print(f"applied {len(reversible)} fixes")


if __name__ == "__main__":
    main()
