#!/usr/bin/env bash
# Did USER approve a comment? Prints every reaction on it, exits 0 only if USER's
# APPROVE_EMOJI is among them.
#
#   approved.sh https://github.com/toumix/desire/pull/23#issuecomment-5117077651
#   approved.sh https://github.com/discopy/discopy/pull/487#discussion_r2280112233
#
# Why a script rather than a tool call: the GitHub MCP tools return a comment's body,
# author and timestamps but never its reactions, and WebFetch against api.github.com
# 403s because GitHub rejects requests with no User-Agent. Reactions on a public repo
# are an unauthenticated GET, so curl is enough — no token, no scope.
#
# A reply from USER on the thread is the simpler tell. Check that first; this is for
# the silent case, where a :rocket: is the whole signal.
set -uo pipefail

USER_LOGIN="${USER_LOGIN:-toumix}"        # USER in AGENTS.md ## Config
APPROVE_EMOJI="${APPROVE_EMOJI:-rocket}"  # APPROVE_EMOJI, likewise

url="${1:-}"
[ -n "$url" ] || { echo "usage: ${0##*/} <comment-url>" >&2; exit 2; }

[[ "$url" =~ ^https://github\.com/([^/]+/[^/]+)/(pull|issues)/[0-9]+#(issuecomment-|discussion_r)([0-9]+)$ ]] || {
  echo "not a comment URL (want …#issuecomment-<id> or …#discussion_r<id>): $url" >&2
  exit 2
}
repo="${BASH_REMATCH[1]}"
id="${BASH_REMATCH[4]}"
# the two live on different endpoints: #issuecomment- is the thread, #discussion_r a diff line
[ "${BASH_REMATCH[3]}" = "issuecomment-" ] && kind=issues || kind=pulls

json=$(curl -sS -H "User-Agent: curl" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$repo/$kind/comments/$id/reactions") || exit 1

# an error comes back as an object, a result as an array — say so rather than printing "none"
if [ "$(jq -r 'type' <<<"$json")" != "array" ]; then
  echo "github: $(jq -r '.message // "unexpected response"' <<<"$json")" >&2
  exit 1
fi

jq -r '.[] | "\(.content) by \(.user.login)"' <<<"$json"
jq -e --arg u "$USER_LOGIN" --arg e "$APPROVE_EMOJI" \
  'any(.[]; .user.login == $u and .content == $e)' <<<"$json" >/dev/null
