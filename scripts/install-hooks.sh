#!/bin/sh
# Installs the project's git hooks into .git/hooks (hooks themselves aren't
# tracked by git, so this needs to be re-run once per clone/checkout).
set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
cp "$REPO_ROOT/scripts/hooks/pre-commit" "$REPO_ROOT/.git/hooks/pre-commit"
chmod +x "$REPO_ROOT/.git/hooks/pre-commit"
echo "Installed pre-commit hook (BOM / mojibake check) into .git/hooks/pre-commit"
