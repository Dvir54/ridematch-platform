#!/usr/bin/env bash
# Creates one worktree + branch per session in a temporary sibling folder
# (../<repo>-worktrees/backend, frontend, tests), puts the shared .env into each,
# and prints the command to start each session.
# Run from the repo root, on main, after the first commit. Works in Git Bash (Windows), WSL, macOS and Linux.
# Re-run it any time you change .env: on Windows it copies .env into the worktrees, so they need refreshing.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
PARENT="$(dirname "$ROOT")"
WT_BASE="$PARENT/$(basename "$ROOT")-worktrees"
mkdir -p "$WT_BASE"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) WINDOWS=1 ;;
  *) WINDOWS=0 ;;
esac

[ -f "$ROOT/.env" ] || { echo "Missing .env. Run: cp .env.example .env and fill it in."; exit 1; }
[ "$(git -C "$ROOT" branch --show-current)" = "main" ] || { echo "Run this from the main branch."; exit 1; }

for role in backend frontend tests; do
  dir="$WT_BASE/$role"
  if [ -d "$dir" ]; then
    echo "exists: $dir (worktree skipped, .env refreshed)"
  else
    git -C "$ROOT" worktree add "$dir" -b "feat/$role"
  fi
  if [ "$WINDOWS" = 1 ]; then
    rm -f "$dir/.env"; cp "$ROOT/.env" "$dir/.env"   # symlinks need admin/dev-mode on Windows, so copy
  else
    ln -sf "$ROOT/.env" "$dir/.env"
  fi
done

winpath() { if [ "$WINDOWS" = 1 ]; then cygpath -w "$1"; else printf '%s' "$1"; fi; }

launch() {
  local role="$1"
  local dir; dir="$(winpath "$WT_BASE/$role")"
  local prompt="You are @$role. Read CLAUDE.md, docs/roles/$role.md, PLAN.md and all of contracts/. Then do your Phase 1 tasks."
  if [ "$WINDOWS" = 1 ]; then
    printf '  cd "%s"; claude --name %s --permission-mode acceptEdits "%s"\n' "$dir" "$role" "$prompt"
  else
    printf '  cd "%s" && claude --name %s --permission-mode acceptEdits "%s"\n' "$dir" "$role" "$prompt"
  fi
}

echo
echo "Worktrees ready. Open 3 terminal tabs$( [ "$WINDOWS" = 1 ] && echo ' (PowerShell)') and run one command in each:"
echo
launch backend
launch frontend
launch tests
cat <<'MSG'

Keep all three in the same permission mode, so their messages are delivered without approval prompts.
Check with /list-agents in any session.
MSG
[ "$WINDOWS" = 1 ] && echo "Note: .env was COPIED into each worktree. After editing the main .env, re-run this script."
exit 0
