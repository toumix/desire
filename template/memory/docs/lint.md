# Memory linter

Install and run from the memory clone (Python 3.10+):

```sh
python -m pip install -r requirements-lint.txt
python scripts/lint_memory.py
python -m unittest discover -s tests -v
```

Fill in `config.env` before running the linter in a new memory clone.
`WORK/TEMPLATE.md` remains in place as a shape and is exempt from numbered-note
validation.

The default run is offline. Diagnostics are `file:line: rule: explanation`.
Exit **0** means the requested checks passed, **1** means rule violations,
and **2** means an incomplete audit, including unreadable GitHub repositories,
authentication failures, rate limits or network failures. Findings already
collected are still printed when another check is incomplete.

## Enforced rules

These checks implement the existing WORK template and the Memory / One file per
open item sections of DESIRE_REPO's AGENTS.md and OPERATIONS.md, plus the board's
own line limit. The rules remain authoritative there.

| Check | Enforcement |
| --- | --- |
| Board | README stays strictly under 200 lines |
| WORK naming | `WORK/<configured repo name>/<positive item number>.md`, matching title |
| WORK fields | Exactly `whose`, `does`, `needs`, `touches`, `blocks`, in that order, each with an explicit answer; rejects the old `state` field |
| Read date | Valid, non-future `read YYYY-MM-DD` on `whose` |
| Turn log | One to five dated turns, newest first, each with a phase/person and description |
| Conflict markers | Reject unresolved merge markers outside code examples |
| Local links | CommonMark inline/reference links, images, autolinks and bare URLs; local paths exist, stay inside the repo, and Markdown fragments match headings or explicit anchors |
| GitHub (opt-in) | Notes for authored/adopted open PRs and open items cited in notes; no notes for closed items; flag read dates older than GitHub's item update date |
| External links (opt-in) | HTTP HEAD with GET fallback for servers rejecting HEAD; follows redirects; 404/410 are findings; other failures mean unverified, not clean |

The GitHub comparison reads every page of open issues and PRs for each WORK_REPO.
It also resolves qualified references across note directories and GitHub item URLs.
Unrelated open items need no note. Repo basenames must be unambiguous in config.
Freshness compares whole UTC dates, like the existing sweep: an update on the
same day does not prove staleness. Legacy notes with a read date on `state` still
get this comparison while failing the structural check.

## Online audit

```sh
python scripts/lint_memory.py --github
python scripts/lint_memory.py --external-links
python scripts/lint_memory.py --github --external-links --timeout 10
```

GitHub reads use `GITHUB_TOKEN` or `GH_TOKEN`, with read access to every configured
WORK_REPO, including private repos. The default Actions token cannot read all
those repos. No token is sent to external link targets. A private URL returning
404 may be inaccessible rather than deleted; inspect access before changing it.
External fragments and comment contents are not checked; the URL's HTTP resource
is what gets verified. Raw HTML links are not parsed. Code examples are excluded.

CI runs tests and the offline linter on PRs and main pushes. Online checks are
manual workflow-dispatch inputs, with no timer and no secrets on pull-request
runs. Set `MEMORY_LINT_TOKEN` to a token with access to the WORK_REPOS to use the
GitHub input. Each request has a timeout; the online job also has a 15-minute
limit. A cancelled or timed-out job is incomplete.

## Existing debt and limits

CI reports existing violations too: there is no silent baseline or automatic rewrite.
Re-read an item before updating its date; check its live state before deleting a
note. Fixing formatting alone must not claim that an item was re-read.

A linter cannot establish whether prose is accurate, whether a turn touched an
unrecorded item, whether a board entry is truly cross-cutting, whether a review
updated OTHERS, or whether a `needs` answer is the right decision. Those remain
review responsibilities. Historical mentions of state inside turn logs are
allowed. The existing sweep remains responsible for approvals, unanswered threads,
waiting issues and the day PR; this linter does not replace it.
