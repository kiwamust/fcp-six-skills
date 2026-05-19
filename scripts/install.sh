#!/usr/bin/env bash
# Install fcp-six-skills into Claude Code or Cursor skills directories.
#
# Security: run only from a trusted clone (official repo or your fork).
# This script creates symlinks under ~/.claude/skills or .cursor/skills.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Refuse if this tree is not a git checkout (reduces curl|bash hijack risk).
if [[ ! -d "$REPO_ROOT/.git" ]]; then
  echo "error: $REPO_ROOT is not a git repository; aborting" >&2
  exit 1
fi
TARGET="${1:-claude}"
DEST=""

case "$TARGET" in
  claude)
    DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
    ;;
  cursor)
    DEST="${CURSOR_SKILLS_DIR:-$PWD/.cursor/skills}"
  ;;
  *)
    echo "Usage: $0 [claude|cursor]" >&2
    echo "  claude  -> ~/.claude/skills (default)" >&2
    echo "  cursor  -> ./.cursor/skills (run from project root)" >&2
    exit 1
    ;;
esac

mkdir -p "$DEST"

for skill_dir in "$REPO_ROOT"/skills/*/; do
  name="$(basename "$skill_dir")"
  link_path="$DEST/$name"
  if [[ -e "$link_path" && ! -L "$link_path" ]]; then
    echo "skip $name: $link_path exists and is not a symlink (remove manually)" >&2
    continue
  fi
  ln -sfn "$skill_dir" "$link_path"
  echo "linked $name -> $skill_dir"
done

echo "done: $DEST"
