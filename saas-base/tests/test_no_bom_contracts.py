from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = [
    PROJECT_ROOT / "app",
    PROJECT_ROOT / "alembic",
    PROJECT_ROOT / "tests",
]


def iter_python_files():
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" not in path.parts:
                yield path


class NoBomContractsTest(unittest.TestCase):
    def test_python_sources_do_not_contain_utf8_bom(self):
        offenders = []
        for path in iter_python_files():
            content = path.read_bytes()
            if content.startswith(b"\xef\xbb\xbf") or b"\xef\xbb\xbf" in content:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(
            offenders,
            [],
            "Python source files must be UTF-8 without BOM: " + ", ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()