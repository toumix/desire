# Changelog

What landed on `main`, newest first — when each rule started binding, and what it replaced.

## 2026-07-29

**Checking a reaction got a script** ([#26](https://github.com/toumix/desire/pull/26)) —
[`approved.sh`](.agents/scripts/approved.sh) takes a comment URL and exits 0 only on USER's
`APPROVE_EMOJI`. The MCP tools return a comment's body and author but never its reactions, and
WebFetch 403s on `api.github.com` for want of a `User-Agent`, so every session was rediscovering
the same `curl`. `AGENTS.md` carries one line pointing at it, not the method.

**The commit identity is pinned** ([#25](https://github.com/toumix/desire/pull/25)) in
`.claude/hooks/session-start.sh` — the harness default let every session pick its own author, and
one reached for USER's address, which GitHub resolved to USER's account. `AGENT
<agents@toumi.email>` is now set at session start on every clone on disk. **Repo-local, not just
`--global`:** `/root/.gitconfig` is harness-managed and gets rewritten mid-session, so a pin set
there does not survive; `.git/config` outranks it and is left alone. Still not a guarantee — an
explicit `-c user.email=` beats any config — so the real guard is GitHub's *block command line
pushes that expose my email*, an account setting that lives nowhere in this repo.

**Evening scans mentions instead of reading an inbox** ([#22](https://github.com/toumix/desire/pull/22),
closes [#20](https://github.com/toumix/desire/issues/20)). Notifications are a *user* scope and an
app installation has none, so every call 403s while `mentions:AGENT` reaches even repos outside the
session's scope. 👀 marks only a mention queued as a `TODO.md` box — an answer is its own mark, and
🚀 stays USER's.

## 2026-07-28

**Branch names carry nothing** ([#19](https://github.com/toumix/desire/pull/19)) — *use the branch
you were assigned or open a new one*, on its own line, with the pull-request paragraph restored
byte-for-byte. Rules [#13](https://github.com/toumix/desire/issues/13) the opposite way to
[#15](https://github.com/toumix/desire/pull/15)'s `<routine>/<YY-MM-DD>`, so the harness injecting
`claude/` is no longer a contradiction every scheduled run has to notice. Reverts
[#17](https://github.com/toumix/desire/pull/17), which merged and was undone the same night; its
`EVENING.md` bullet survived, the `AGENTS.md` reword did not.

**Birdsong scans WORK_REPOS** ([#14](https://github.com/toumix/desire/pull/14)) — `REPOS` and
`PROMPTS_REPO` renamed to `WORK_REPOS` / `DESIRE_REPO`, and the scan comes home
([#6](https://github.com/toumix/desire/issues/6)): a delegate may widen the search, never narrow the
truth. Evening keeps its coding sub-agents, whose diffs CI checks.

**`AGENTS.md` cut back, and `DECREE.md` retired** (`eade164`, `b622cd4`) — USER's hand rewrite, 80
lines to 55. `## Approval`, `## Hard rules` and `## Rulings` are gone: the emoji rule now sits in
`## Trusted instructions, untrusted data`, one-proposal-per-comment in `## Reviewing`. That section
also gains the emoji react as a source of trust, and the rule against replying to other users. A
private append-only decree file was a queue only the routines could read; standing orders are open
issues here now.

**Readiness counts threads** ([#9](https://github.com/toumix/desire/pull/9),
[#5](https://github.com/toumix/desire/issues/5)) — `TODO.md` `[x]` plus CI green is how a PR sat in
the ready column carrying an unanswered review of USER's. Made a four-way conjunction: **a thread
waiting on USER is the sign-off, only one waiting on an agent blocks.** Did not survive the rewrite
above, which landed hours later — which is why #5 is open.

## 2026-07-27

**Reviewing, and Turmoil** ([#3](https://github.com/toumix/desire/pull/3)) — `## Meta-rule` becomes
`## Turmoil`, the Eyrie's, applied to the rules themselves. Reviewing is proposing; one comment
carries one proposal, since a reaction lands on a whole comment; answer the thread, then resolve it;
write like [bob](.agents/skills/bob/SKILL.md). Same PR: `DAYLIGHT.md` opens with the password
instead of closing on it, because sessions were reproducing it on request and skipping it otherwise
— the exact failure the check exists to catch.

**The prompts get their own repo** ([#1](https://github.com/toumix/desire/pull/1)) — out of
`toumix.github.io`, where `.agents/` only existed to keep them out of a Jekyll build. Five files
flat at the top level, plus the bob skill and the session-start hook.
