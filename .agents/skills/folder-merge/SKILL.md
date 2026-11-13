---
name: folder-merge
description: Go through AGENT's open pull requests on a repo with personal folders, merge the ones confined to its own folder that nobody is working on, and ask USER through the question interface about the ones in doubt. Use when USER says "merge my personal-folder PRs", "go through the PRs in my folder" or "which of my pages can land", and before saying which finished pages still wait.
---

# Folder merge

Some repos give each author a folder under `content/`, mapped from logins in
`.github/personal-folders.json`: a pull request confined to its author's folder is approved by an
App and merged by its author, with no human review. This sorts ours. Every other pull request
stays under [Merging on approval](../../../OPERATIONS.md#merging-on-approval).

Run from the MEMORY_REPO clone, so `config.env` is found (else `--config FILE` or `AGENTS_CONFIG`):

```shell
python3 <DESIRE_REPO clone>/.agents/skills/folder-merge/folder_merge.py owner/repo [--quiet HOURS]
```

One line per open pull request AGENT wrote or ADOPTED_PRS lists, oldest first: the full head SHA,
the branch, draft or ready, hours since the last push, then `-> verdict (reasons)`. Read-only.
Exit 0 when none says `ask` or `blocked`, 1 when one does, 2 when a read failed (`n/a`).

| verdict | when, first match | what to do |
|---|---|---|
| `outside` | a changed path, either side of a rename, is not under the folder | nothing: it waits on USER's approving review |
| `active` | the last push is under `--quiet` hours old, 24 by default | nothing, and no question |
| `blocked` | the base is not the default branch; a conflict; a check failed, pending or never ran; a thread waits on an agent; no approval | fix it, below |
| `ask` | the body or an added line says not to merge ("not to merge automatically", "do not merge"); an open checkbox in the body; a thread waits on USER; a person commented, or reviewed with words, after the head commit was written, or edited a comment since; `mergeable` unknown | ask USER, below |
| `merge` | none of these: a draft does not hold it | merge it, below |

The last push is the latest of the head commit's date, the first check run on it and the last
force-push: GitHub keeps no push time, and a commit can be older than its push.

The script sees GitHub alone. Before acting on a `merge`, read the item's `WORK/` note and, where
the harness lists sessions, the running ones: a session still on that branch makes it `active`,
and a note naming a pull request it lands after or a run still going makes it an `ask`.

## Merge

In the order printed, one at a time:

1. A draft is marked ready first. That fires the App's check, so run the script again.
2. When it says `merge` again, merge with the SHA it prints as `expectedHeadSha`, as a merge commit.
3. Run the script again before the next one: a merge can conflict the next head, on a shared
   index page above all.

## Ask

One question per pull request, through the harness's question interface (`AskUserQuestion` in
Claude Code), up to four a call. The question says in a few words what the pull request is and
gives the script's reason; the options are merge, leave it, and what else the reason suggests,
the recommended one first. USER's answer is a live turn: act on it, and write it in the note.
A session with no question interface leaves every `ask` and names them in its day PR comment.

## Blocked

- **A base that is another pull request's branch**: that one merges first. Then set this one's
  base to the default branch and run the script again.
- **A conflict or a base moved on**: [remerge](../remerge/SKILL.md), then push. The push makes it
  `active`: it comes back on a later run.
- **A failed check, a thread on an agent**: the work is the pull request's own; do it there.
- **No approval** on a confined pull request: the App's check failed or never ran. Read its run
  before anything else.

## After

A merged item's `WORK/` note is deleted, and each one asked about gets its log line
([Memory](../../../AGENTS.md#memory)); [work-notes](../work-notes/SKILL.md) checks both.
