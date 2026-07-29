#!/bin/bash
# SessionStart hook — install the GitHub CLI (and jq) for the scheduled routines.
# Best-effort: it must NEVER block session start.
#
# Installs from Ubuntu's own apt repo (gh lives in noble universe) — the agent proxy
# allows archive.ubuntu.com but 403s github.com / cli.github.com release downloads.
set -uo pipefail   # deliberately no -e — an install failure must not abort the hook

# web / remote sessions only (the routines); do nothing on a local dev machine
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

log() { echo "session-start: $*" >&2; }

# Pin the commit identity. AGENT is what should author agent commits, and leaving it to
# the harness default means every session picks its own — one reached for USER's address
# instead, which GitHub resolved to USER's account (see CHANGELOG.md, 2026-07-29).
# Guarded by CLAUDE_CODE_REMOTE above, so a developer's own machine is never touched.
#
# --global alone does NOT hold: /root/.gitconfig is harness-managed and gets rewritten
# mid-session — a pin set there was found reverted ten minutes later. Repo-local config
# outranks global and is not managed, so set both: local on every clone already on disk,
# global as the fallback for anything cloned after this runs.
git config --global user.name  "toumix-agents"
git config --global user.email "agents@toumi.email"
for gitdir in "$(dirname "${CLAUDE_PROJECT_DIR:-$PWD}")"/*/.git; do
  [ -d "$gitdir" ] || continue   # no clones yet, or the glob matched nothing
  repo="${gitdir%/.git}"
  git -C "$repo" config --local user.name  "toumix-agents"
  git -C "$repo" config --local user.email "agents@toumi.email"
  log "identity pinned in $repo"
done

pkgs=()
command -v jq >/dev/null 2>&1 || pkgs+=(jq)
command -v gh >/dev/null 2>&1 || pkgs+=(gh)

if [ ${#pkgs[@]} -gt 0 ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >/dev/null 2>&1 || true
  if apt-get install -y -qq "${pkgs[@]}" >/dev/null 2>&1; then
    log "installed: ${pkgs[*]}"
  else
    log "apt install failed for: ${pkgs[*]} — the GitHub MCP tools remain available"
  fi
fi

# gh reads GH_TOKEN / GITHUB_TOKEN automatically (both are set in this environment)
[ -n "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ] || log "note: no GH_TOKEN/GITHUB_TOKEN in env — gh will be unauthenticated"

command -v gh >/dev/null 2>&1 && log "$(gh --version | head -1)" || true
exit 0
