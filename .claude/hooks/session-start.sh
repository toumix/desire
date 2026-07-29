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

# Pin the commit identity — local too, the global one gets rewritten (CHANGELOG.md).
. "${CLAUDE_PROJECT_DIR:-$PWD}/.agents/scripts/config.sh"
git config --global user.name  "$AGENT"
git config --global user.email "$AGENT_EMAIL"
for gitdir in "$(dirname "${CLAUDE_PROJECT_DIR:-$PWD}")"/*/.git; do
  [ -d "$gitdir" ] || continue
  repo="${gitdir%/.git}"
  git -C "$repo" config --local user.name  "$AGENT"
  git -C "$repo" config --local user.email "$AGENT_EMAIL"
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
