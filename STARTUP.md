# STARTUP.md

🌱 Startup runs once, before the first turn, and is the only prompt a stranger can run.
The link to this repo is the whole input; this file is the whole plan. `CLAUDE.md` does not
import it — it is read on demand, by you, now, and never again.

You are setting up the person in this session — call them USER — with their own pipeline:
a public fork of this repo (the rules), a private `memory` repo (the work), a second GitHub
account for the agents, and the schedules that fire 🐦 Birdsong and 🌙 Evening.

## Before you touch anything

- **Check what you can do.** Which GitHub account is this session authenticated as (`gh auth
  status`, or a "who am I" call on whatever GitHub tooling you have)? If it is not USER's own
  account with write access, stop and say what they need to connect — every step below assumes it.
- **Ask once, not step by step.** In one batch: their GitHub login, the name for the memory repo
  (`memory` unless they say otherwise), which repos the agents will work in, whether an agent
  account already exists. Then go quiet and work.
- **Look for the memory repo before assuming this is a cold start.** If it already exists, today's
  file in `TURNS/` is where the last attempt got to: read it first and resume from it. Setup spans
  a coffee break, a verification email, and sometimes a new session — this file is the plan, that
  file is the progress, and starting over from step 1 is the failure this avoids.
- **Every step is idempotent anyway.** Check the end state before doing it — fork exists?
  collaborator already? A log can be one step stale; GitHub cannot.
- **[you]** is yours to do with tools. **[USER]** is a human step — a captcha, a mailbox, an OAuth
  consent screen. Do not try to automate those, and do not pretend they are done.

## The steps

1. **[USER] The agent account.** Start this first, it is the only step with a wait in it: a second
   GitHub account, named `<login>-agents` by convention. A plus-addressed email works
   (`you+agents@gmail.com`). Turn on 2FA. While they wait on the verification mail, keep going —
   nothing until step 6 needs it.
2. **[you] Create the memory repo, private**, owned by USER — first, before the fork, because it
   is where the rest of this is written down. Seed it with three files:

   `CLAUDE.md`
   ```
   @AGENTS.md
   @README.md
   ```

   `AGENTS.md`
   ```
   # mixing memory and desire

   The MEMORY_REPO of USER's routines. Two files, each with exactly one lifetime:

   - `TURNS/<date>.md` — the turn journal, write-once, one section per role in firing order.
     It carries what *changed*, not the whole picture.
   - `README.md` — the live board, rewritten every turn. Read it instead of re-deriving it.

   Each turn lands as a pull request titled `<Routine> <date>`, stacked on the previous open
   one, never a push to `main`. The PR review is USER's feedback channel and its comments are
   the short-term memory, discarded when the PR merges.

   Standing orders are open issues on DESIRE_REPO, not a file here.
   ```

   `README.md`
   ```
   # The board

   Rewritten every turn, never appended to: what is ready, what is blocked on what, what is
   behind. State only — conventions are open issues on DESIRE_REPO.

   Nothing has run yet. 🐦 Birdsong writes this for real on its first turn.
   ```

3. **[you] Open today's turn file and write the plan into it** — `TURNS/<date>.md`, one
   `## 🌱 Startup` section, the steps below as `[ ]` checkboxes. Then tick each one **as it lands**,
   with the fact it produced next to it: the fork's URL, the agent login, the cron lines you
   created, anything USER declined or postponed. Push straight to `main`, one push per step: this
   is the one write in the whole pipeline that does not go through a pull request, because the PR
   convention exists to give USER a review surface and here USER is in the room watching.
   A session that dies mid-setup costs one step, not the afternoon — and the first thing 🐦 Birdsong
   ever reads is this file, so what setup skipped arrives as its first turn's context.
4. **[you] Fork this repo** to USER's account, public, same name. Public because the rules are
   the part anyone may read; the fork is theirs to diverge, and `Sync fork` is how later rule
   changes reach them. Never push to the repo you were linked from.
5. **[you] Write the config.** In the fork's `AGENTS.md`, fill `## Config` — `USER`, `AGENT`
   (the step-1 login), `MEMORY_REPO` (step 2), `DESIRE_REPO` (the fork, not upstream), `WORK_REPOS`.
   If they have no work repo yet, leave the list empty and tell them; do not invent one.
   Commit it to `main` while you still can — the next step closes that door.
6. **[USER] Protect `main` on the fork.** Require a pull request, no direct pushes, and if the
   agent account is a collaborator there, no bypass for it. This is not hygiene: `AGENTS.md` trusts
   that branch, so whoever can push to it can rewrite what the agents are allowed to do.
7. **[USER] Invite the agent account** as a collaborator with write access on the fork and on the
   memory repo, then **accept both invitations from the agent account** — an invitation nobody
   accepted looks identical to access, until the first scheduled run fails on it. On WORK_REPOS,
   either the same invitation or let the agents work from their own fork; USER decides.
8. **[USER] Connect the agent account to the model.** Signed in as the agent and not as USER: sign
   the agent account into Claude or Codex, on whatever plan the scheduled runs need, and connect
   its GitHub identity there. The two accounts stay separate on purpose — USER approves, the agent
   acts, and the PR between them is the seam.
9. **[USER] Then grant that model's GitHub app the repositories.** A separate system, separately
   done, and this is the step that eats an afternoon: step 8 connects an *account*, this one hands
   over *repos*, and each one looks finished while the other is missing. Install the provider's
   GitHub app **on the account that owns each repo** — USER owns the fork and the memory repo, so
   that grant is made from USER's account and must name both by hand if the install is not
   all-repositories; the agent being a collaborator does not carry it. Same again for every
   WORK_REPO, from whoever owns it. The symptom of stopping at step 8 is a session that opens
   fine and sees no repositories; the symptom of a half-done step 9 is a run that reads a repo
   and cannot push to it.
10. **Schedule the routines.** 🐦 Birdsong fires before USER's day, 🌙 Evening after it; 🌤️ Daylight
   is never scheduled, it is whatever session USER opens. If this session has scheduler tools, make
   them now, against the agent account and the fork: Birdsong ~06:00 and Evening ~00:00 in USER's
   timezone, converted to **UTC** in the cron expression. If it does not, hand USER the two cron
   lines and where to paste them. Either way, tell them plainly: the schedule is the one piece of
   config that does not live in git, so a change to the prompts is not a change to the scheduler.
11. **[you] Verify, then hand over.** Walk the log — fork public with the config committed and
    `main` protected, memory repo private and seeded, both invitations accepted, agent account
    connected to the model *and* the GitHub app granted every repo by name, both schedules created.
    The last two are worth a live check rather than a claim: from a session on the agent account,
    have it list the repos it can see, push a throwaway branch to the memory repo, and read its own
    notifications — the routines sweep that inbox, and a token without the `notifications` scope
    fails it silently, with a `mentions:@me` search as the fallback. Leave every
    unfinished box unticked with a line saying what is missing — an unticked box is the handover,
    and it is the first thing the pipeline reads about itself. Report anything you could not
    confirm as not done, not as probably fine.

## Do not

- Do not push to the repo you were linked from, or open a PR there. It is upstream; USER's fork is
  the working copy.
- Do not create the GitHub account, click the consent screen, or accept the invitation for them.
  Guide, never impersonate — and never ask for their password or a 2FA code.
- Do not put anything private in the fork. The memory repo is the private one, and it is private
  because everything in it is trusted.
- Do not add `STARTUP.md` to `CLAUDE.md`. Every line imported there is loaded into every session
  forever; this file is done after today.
- Do not pick a side on an unclear answer. `## Turmoil` already applies to you: ask USER.

## Then stop

Setup is over and does not run again. Leave USER with the three things that are now theirs:
review the agents' PRs, react 🚀 on a comment to approve it, open a 🌤️ Daylight session when they
want to design something. Tell them to open that session on the fork and ask it for its
password — `AGENTS.md`, `BIRDSONG.md`, `DAYLIGHT.md` and `EVENING.md` are loaded from now on, and
the password coming back is how they know it.
