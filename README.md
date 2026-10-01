# RideMatch

A ride-sharing web app: a FastAPI monolith + React/Vite/TS, with Clerk auth.
It's built by three parallel Claude Code sessions (backend / frontend / tests). See `CLAUDE.md` and `PLAN.md`.

## Quick start (Windows)
Requires Git for Windows, Docker Desktop, uv, Node 20+ and Claude Code v2.1.234+.
```bash
# in Git Bash, inside ridematch-platform/
git init -b main && git add . && git commit -m "chore: project setup and contract v0.3.0"
cp .env.example .env              # fill in Clerk + Mapbox keys
docker compose up -d              # Postgres + Redis (Docker Desktop must be running)
./scripts/setup-worktrees.sh      # creates ../ridematch-platform-worktrees/{backend,frontend,tests} + prints launch commands
# ...at the very end, after everything is merged:
./scripts/remove-worktrees.sh     # deletes the worktrees; only this repo remains
```

| Path | What |
|---|---|
| `contracts/` | API spec, DB schema, rules: the source of truth |
| `docs/SYSTEM_DESIGN.md` | Original design doc |
| `docs/roles/` | Instructions per session |
| `PLAN.md` | Phases, tasks per session, gates |
