# opencode-telegram-bot

Telegram → [opencode](https://opencode.ai) bridge. Message the bot and it runs
`opencode run` in a working directory of your choosing; opencode edits files,
runs commands, and the output streams back to Telegram as it's produced.

Access is restricted to a single allowlisted Telegram user id — anyone else's
messages are silently ignored, since a message can make opencode run shell
commands and edit files on the host.

## Setup

```bash
pip install python-telegram-bot
cp .env.example ~/.opencode-bot.env   # fill in TELEGRAM_BOT_TOKEN / TELEGRAM_USER_ID / etc.
python opencode_telegram_bot.py
```

See `.env.example` for all supported variables.

### Persistent service (systemd)

`systemd/opencode-bot.service` (+ `override.conf` for `PATH`) mirrors what's
running in production: replace `YOUR_USER` with your username, drop both files
under `/etc/systemd/system/`, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now opencode-bot.service
```

## Commands

| Command | What it does |
|---|---|
| `/repo <path>` | switch the active working directory (starts a fresh opencode session there) |
| `/model <slug>` | switch model, e.g. `openrouter/anthropic/claude-sonnet-4.5` |
| `/new` | start a fresh opencode session in the current repo, dropping prior context |
| `/diff` | show the last commit's diff |
| `/undo` | `git reset --hard HEAD~1` in the active repo — careful |
| `/status` | active repo, model, session id, `git status -sb` |
| anything else | sent straight to opencode as a message |

## How it works

Each message shells out to `opencode run --auto --format json --dir <repo>`,
passing `--session <id>` once a session exists so conversation context
persists across messages in the same repo (`/repo` or `/new` reset it).
`--format json` streams one JSON event per line; the bot forwards each `text`
part and each `tool_use` part to Telegram as soon as it arrives, rather than
buffering the whole run before replying.

`--auto` auto-approves opencode's permission prompts, since there's no
terminal on the other end to answer them — this is what makes running it
non-interactively over Telegram possible, and also why the allowlist above
matters.
