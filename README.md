# desire

> *Lilacs out of the dead land, mixing*
> 
> *Memory and desire, stirring*

Software engineering prompts inspired by the asymmetric board game Root:

- 🐦 [Birdsong](BIRDSONG.md) plans, asynchronously, before the day starts
- 🌤️ [Daylight](DAYLIGHT.md) activates in every interactive session you open
- 🌙 [Evening](EVENING.md) reviews and implements, overnight, what you approved

[AGENTS.md](AGENTS.md) is the operating base they all follow: config, the two layers of memory,
what authorizes a change. It is deliberately short (under a hundred lines with the phase files)
because every line of it is loaded into every session. Some guiding principles:

- **Asynchronous feedback via GitHub PRs**, you don't need an interactive chat to get stuff done.
- **Synchronous feedback via chat sessions**, but they start with the bigger picture in mind.
- **Agents open issues when the rules clash**, at your request they open a PR with updated rules.

## Get started

Paste this into a fresh session, with whichever model you use:

> Set me up with https://github.com/toumix/desire — read `STARTUP.md` and walk me through it.

🌱 [Startup](STARTUP.md) does the rest: it forks this repo, creates your private `memory` repo,
writes your config, and walks you through the parts only a human can do — the agents' GitHub
account, the invitations, the authorisations. It is not imported by `CLAUDE.md`: it runs once.

By hand, it is three steps:

1) Open a new GitHub account for your agents, add it as collaborator to your fork for this repo.
2) Create a new GitHub repo (e.g. called `memory`) and add it to the config block in `AGENTS.md`.
3) Integrate it to your model provider, adding the `memory` and `desire` repos alongside your work.

**Pro tip:** Ask your 🌤️ Daylight session for its password to check it actually loaded the prompt.
🌱 Startup has one too, for the same reason — it should say it before it does anything.
