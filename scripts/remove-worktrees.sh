#!/usr/bin/env bash
# Run at the end (after everything is merged into main), from the repo root.
# Removes the 3 worktrees and their temporary folder, so only this repo is left.
# git refuses to remove a worktree with uncommitted changes, so nothing gets lost silently.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
WT_BASE="$(dirname "$ROOT")/$(basename "$ROOT")-worktrees"

for role in backend frontend tests; do
  dir="$WT_BASE/$role"
  if [ -d "$dir" ]; then
    rm -f "$dir/.env"                     # the copied .env is ignored by git but would block removal
    git -C "$ROOT" worktree remove "$dir" && echo "removed: $dir"
  fi
done
git -C "$ROOT" worktree prune
rmdir "$WT_BASE" 2>/dev/null && echo "removed: $WT_BASE" || true

for role in backend frontend tests; do
  if git -C "$ROOT" branch --merged main | grep -q "feat/$role"; then
    echo "feat/$role is merged into main (delete it with: git branch -d feat/$role)"
  else
    echo "WARNING: feat/$role is NOT fully merged into main. Kept as is."
  fi
done
