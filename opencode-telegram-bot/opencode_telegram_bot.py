#!/usr/bin/env python3
"""
Telegram → opencode bridge.

Each plain message is sent to `opencode run` in the active repo. Unlike a
one-shot CLI call, opencode keeps a real session per repo, so the bot passes
--session to continue the same conversation across messages until you /repo
elsewhere or /new.

Setup:
    source ~/.aider-bot.env         # TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID
    source ~/.opencode-bot.env      # OPENCODE_REPO, OPENCODE_MODEL, OPENCODE_BIN
    python opencode_telegram_bot.py

Commands:
    /repo <path>    switch active repo (starts a fresh session there)
    /model <slug>   switch model (e.g. openrouter/anthropic/claude-sonnet-4.5)
    /new            start a fresh opencode session in the current repo
    /diff           show last commit diff
    /undo           revert last commit (git reset --hard HEAD~1 — careful)
    /status         current repo, model, session, git status
"""

import asyncio
import json
import os
import shlex
import subprocess
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------- config
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER = int(os.environ["TELEGRAM_USER_ID"])

OPENCODE_BIN = os.environ.get("OPENCODE_BIN", str(Path.home() / ".opencode" / "bin" / "opencode"))
DEFAULT_REPO = os.environ.get("OPENCODE_REPO", os.environ.get("AIDER_REPO", str(Path.home())))
DEFAULT_MODEL = os.environ.get("OPENCODE_MODEL", "openrouter/anthropic/claude-sonnet-4.5")
OPENCODE_TIMEOUT = int(os.environ.get("OPENCODE_TIMEOUT", "600"))

STATE_FILE = Path.home() / ".cache" / "opencode-bot" / "state.json"

state = {"repo": DEFAULT_REPO, "model": DEFAULT_MODEL, "session_id": None}
run_lock = asyncio.Lock()

TG_LIMIT = 4000


def load_state() -> None:
    if STATE_FILE.exists():
        try:
            state.update(json.loads(STATE_FILE.read_text()))
        except (json.JSONDecodeError, OSError):
            pass


def save_state() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


# ---------------------------------------------------------------- helpers
def authorized(update: Update) -> bool:
    return update.effective_user is not None and update.effective_user.id == ALLOWED_USER


async def send_chunked(update: Update, text: str) -> None:
    text = text.strip() or "(no output)"
    for i in range(0, len(text), TG_LIMIT):
        chunk = text[i : i + TG_LIMIT]
        try:
            # Legacy Markdown renders opencode's own links/code fences and is
            # more forgiving of unescaped punctuation than MarkdownV2;
            # wrapping every message in a code fence (as before) flattened
            # everything to monospace and made links unclickable.
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            # fall back to plain text if markdown parsing bites
            await update.message.reply_text(chunk)


def run_cmd(args: list[str], cwd: str, timeout: int = 60) -> str:
    try:
        out = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return (out.stdout + "\n" + out.stderr).strip()
    except subprocess.TimeoutExpired:
        return f"⏱ timed out after {timeout}s"


async def stream_opencode(message: str, on_chunk) -> None:
    """Run opencode and await on_chunk(text) for each text/tool event as it
    arrives, instead of waiting for the whole run to finish."""
    args = [
        OPENCODE_BIN, "run", message,
        "--auto",                  # never block on permission prompts
        "--format", "json",
        "-m", state["model"],
        "--dir", state["repo"],
    ]
    if state["session_id"]:
        args += ["--session", state["session_id"]]

    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=state["repo"],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    got_any = False
    raw_fallback = []

    async def read_events():
        nonlocal got_any
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            line = line.decode(errors="replace").strip()
            if not line.startswith("{"):
                if line:
                    raw_fallback.append(line)
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                raw_fallback.append(line)
                continue
            if ev.get("sessionID") and not state["session_id"]:
                state["session_id"] = ev["sessionID"]
                save_state()
            part = ev.get("part", {})
            if ev.get("type") == "text" and part.get("text"):
                got_any = True
                await on_chunk(part["text"])
            elif ev.get("type") == "tool_use":
                got_any = True
                tool = part.get("tool", "?")
                title = part.get("state", {}).get("title", "")
                await on_chunk(f"🔧 {tool}: {title}")

    try:
        await asyncio.wait_for(read_events(), timeout=OPENCODE_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        await on_chunk(f"⏱ timed out after {OPENCODE_TIMEOUT}s")
        return
    finally:
        if proc.returncode is None:
            await proc.wait()

    if not got_any:
        await on_chunk("\n".join(raw_fallback).strip() or "(no output)")


# ---------------------------------------------------------------- handlers
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    prompt = update.message.text
    if run_lock.locked():
        await update.message.reply_text("⏳ Busy with a previous run, queued...")
    async with run_lock:
        await update.message.reply_text(
            f"🤖 opencode @ {Path(state['repo']).name} [{state['model'].split('/')[-1]}]..."
        )

        async def on_chunk(text: str) -> None:
            await send_chunked(update, text)

        await stream_opencode(prompt, on_chunk)


async def cmd_repo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await update.message.reply_text(f"Active repo: {state['repo']}")
        return
    path = Path(shlex.join(context.args)).expanduser()
    if not path.is_dir():
        await update.message.reply_text(f"❌ {path} is not a directory")
        return
    state["repo"] = str(path)
    state["session_id"] = None
    save_state()
    await update.message.reply_text(f"✅ Repo → {path} (fresh session)")


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await update.message.reply_text(f"Active model: {state['model']}")
        return
    state["model"] = context.args[0]
    save_state()
    await update.message.reply_text(f"✅ Model → {state['model']}")


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    state["session_id"] = None
    save_state()
    await update.message.reply_text("✅ Started a fresh opencode session")


async def cmd_diff(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await send_chunked(update, run_cmd(["git", "show", "--stat", "-p", "HEAD"], state["repo"]))


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    last = run_cmd(["git", "log", "-1", "--oneline"], state["repo"])
    out = run_cmd(["git", "reset", "--hard", "HEAD~1"], state["repo"])
    await send_chunked(update, f"Reverted: {last}\n{out}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    git = run_cmd(["git", "status", "-sb"], state["repo"])
    session = state["session_id"] or "(none yet)"
    await send_chunked(
        update,
        f"repo:    {state['repo']}\nmodel:   {state['model']}\nsession: {session}\n\n{git}",
    )


# ---------------------------------------------------------------- main
def main() -> None:
    load_state()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("repo", cmd_repo))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("diff", cmd_diff))
    app.add_handler(CommandHandler("undo", cmd_undo))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("opencode Telegram bridge running (long polling).")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
