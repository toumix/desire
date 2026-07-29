#!/usr/bin/env bash
# Read CONFIG.md into the environment. Source it, do not run it:
#
#   . "$(dirname "${BASH_SOURCE[0]}")/config.sh"
#
# Each key becomes a variable of the same name, except USER — that one is the shell's
# own, so it lands as USER_LOGIN. WORK_REPOS is a list, not a scalar, and is skipped.
# Anything already set in the environment wins, so a caller can override one value.

_config_md="${CONFIG_MD:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/CONFIG.md}"

_config() {
  sed -nE "s/^- $1[[:space:]]*= \"(.*)\"[[:space:]]*\$/\1/p" "$_config_md" | head -1
}

USER_LOGIN="${USER_LOGIN:-$(_config USER)}"
AGENT="${AGENT:-$(_config AGENT)}"
AGENT_EMAIL="${AGENT_EMAIL:-$(_config AGENT_EMAIL)}"
MEMORY_REPO="${MEMORY_REPO:-$(_config MEMORY_REPO)}"
DESIRE_REPO="${DESIRE_REPO:-$(_config DESIRE_REPO)}"
APPROVE_EMOJI="${APPROVE_EMOJI:-$(_config APPROVE_EMOJI)}"

export USER_LOGIN AGENT AGENT_EMAIL MEMORY_REPO DESIRE_REPO APPROVE_EMOJI
