#!/usr/bin/env python3
"""AGENT's open pull requests confined to its personal folder, each with a
verdict from live GitHub data, read-only: merge, ask, active or blocked.

Usage: folder_merge.py [--quiet HOURS] [--folders PATH] [--json]
                       [--config FILE] <owner/repo>
Exit 0 none says ask or blocked, 1 one does, 2 a read failed.
"""
import argparse
import base64
import concurrent.futures
import datetime
import json
import os
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / "pr-status"))
import pr_status  # noqa: E402  pylint: disable=wrong-import-position

FOLDERS = ".github/personal-folders.json"
HOLD = re.compile(
    r"\bnot to (be )?merged?\b|\b(do not|don't|never) merge\b"
    r"|\bnot (be )?merged? (automatically|before|until)\b", re.I)
OPEN_BOX = re.compile(r"^\s*([-*+]|\d+[.)]) \[ \]", re.M)
ADDED = re.compile(r"^\+(?!\+\+)(.*)$", re.M)


def when(stamp):
    """An ISO timestamp of GitHub as an aware datetime."""
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def folder(repo, login, default, path=FOLDERS):
    """The folder `login` owns under content/, None when it owns none."""
    body = pr_status.get(repo, f"contents/{path}?ref={default}")
    if body is None:
        raise pr_status.Unread(f"no {path}")
    try:
        owners = json.loads(base64.b64decode(body["content"]))
    except (KeyError, TypeError, ValueError):
        owners = None
    if not isinstance(owners, dict):
        raise pr_status.Unread(f"{path} is not a map of logins")
    return owners.get(login)


def outside(files, owned):
    """The changed paths, either side of a rename, outside content/<owned>/."""
    paths = [p for f in files for p in (
        f["filename"], f.get("previous_filename")) if p]
    return sorted(p for p in paths if not p.startswith(f"content/{owned}/"))


def approved(reviews):
    """Whether some reviewer's latest deciding review approves and none asks
    for changes, on any commit: the App approves once and keeps it across
    pushes, and `outside` re-reads the paths of the head."""
    latest = {}
    for review in reviews:
        if review["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[(review.get("user") or {}).get("login")] = review["state"]
    states = set(latest.values())
    return "APPROVED" in states and "CHANGES_REQUESTED" not in states


def holds(pull, files):
    """Whether the body or an added line says not to merge."""
    added = "\n".join(line for f in files
                      for line in ADDED.findall(f.get("patch") or ""))
    return bool(HOLD.search((pull.get("body") or "") + "\n" + added))


def last_push(commit, runs, events):
    """When the head reached the pull request, as near as GitHub says: the
    latest of its commit date, the first check run on it and the last
    force-push."""
    times = [commit["commit"]["committer"]["date"]]
    starts = [run["started_at"] for run in runs if run.get("started_at")]
    times += [min(starts, key=when)] if starts else []
    times += [e["created_at"] for e in events
              if e.get("event") == "head_ref_force_pushed"]
    return max(map(when, times))


def unanswered(comments, reviews, written, setup):
    """Logins of the people, bots and the agent apart, who wrote a comment
    or a review with a body after the head commit was written, or edited
    one since, which no later estimate of its push may hide; the agent is
    AGENT, or USER's account with a footer."""
    said = [(c, c.get("updated_at") or c["created_at"]) for c in comments] + [
        (r, r["submitted_at"]) for r in reviews
        if r.get("body") and r.get("submitted_at")]
    logins = set()
    for post, stamp in said:
        user = post.get("user") or {}
        login = user.get("login") or "ghost"
        agent = login == setup["AGENT"] or (
            login == setup["USER"]
            and pr_status.agent_footer(post.get("body"), setup))
        if not agent and user.get("type") != "Bot" and when(stamp) > written:
            logins.add(login)
    return sorted(logins)


def verdict(s, quiet):
    """(verdict, reasons), first match: active while the last push is under
    `quiet` hours old, blocked on what an agent fixes, ask on what only USER
    settles, else merge."""
    if s["hours"] < quiet:
        return "active", [f"pushed {s['hours']}h ago"]
    blocked = []
    if s["base"] != s["default"]:
        blocked.append(f"base is {s['base']}")
    if s["mergeable"] is False:
        blocked.append("conflict")
    _, failed, pending = s["checks"]
    blocked += [f"failed {', '.join(failed)}"] if failed else []
    blocked += [f"pending {', '.join(pending)}"] if pending else []
    if not s["ran"]:
        blocked.append("no check ran")
    if s["threads"][0]:
        blocked.append(f"{len(s['threads'][0])} thread(s) on agent")
    if not s["approved"]:
        blocked.append("no approval")
    if blocked:
        return "blocked", blocked
    ask = []
    if s["hold"]:
        ask.append("says not to merge")
    if s["boxes"]:
        ask.append(f"{s['boxes']} open box(es) in the body")
    if s["threads"][1]:
        ask.append(f"{len(s['threads'][1])} thread(s) on USER")
    if s["unanswered"]:
        ask.append(f"comment by {', '.join(s['unanswered'])} after the head")
    if s["mergeable"] is None:
        ask.append("mergeable unknown")
    return ("ask", ask) if ask else ("merge", [])


def measure(repo, pull, owned, default, setup, now, wait=time.sleep):
    """One pull request's fields; its paths alone when one is outside."""
    number, sha = pull["number"], pull["head"]["sha"]
    s = {"pr": f"{repo}#{number}", "sha": sha, "title": pull["title"],
         "branch": pull["head"]["ref"]}
    files = pr_status.get(repo, f"pulls/{number}/files")
    s["outside"] = outside(files, owned)
    if s["outside"]:
        s["verdict"], s["reasons"] = "outside", []
        return s
    full = pr_status.mergeable(repo, number, wait)
    runs = pr_status.get(repo, f"commits/{sha}/check-runs", "check_runs")
    commit = pr_status.get(repo, f"commits/{sha}")
    pushed = last_push(commit, runs,
                       pr_status.get(repo, f"issues/{number}/timeline"))
    reviews = pr_status.get(repo, f"pulls/{number}/reviews")
    s.update(
        draft=full["draft"], mergeable=full.get("mergeable"),
        base=full["base"]["ref"], default=default, ran=bool(runs),
        checks=pr_status.checks(
            runs, pr_status.expected(repo, full["base"]["ref"]), now),
        threads=pr_status.split_threads(
            pr_status.threads(repo, number), setup),
        approved=approved(reviews),
        hours=int((now - pushed).total_seconds() // 3600),
        hold=holds(full, files),
        boxes=len(OPEN_BOX.findall(full.get("body") or "")),
        unanswered=unanswered(
            pr_status.get(repo, f"issues/{number}/comments"), reviews,
            when(commit["commit"]["committer"]["date"]), setup))
    return s


def line(s):
    """One text line for a measured pull request."""
    head = f"{s['pr']} @{s['sha']} {s['branch']}"
    if s["verdict"] == "outside":
        more = f" (+{len(s['outside']) - 1})" if len(s["outside"]) > 1 else ""
        return f"{head} -> outside ({s['outside'][0]}{more})"
    if s["verdict"] == "n/a":
        return f"{head} -> n/a ({s['reasons'][0]})"
    why = f" ({'; '.join(s['reasons'])})" if s["reasons"] else ""
    return (f"{head} {'draft' if s['draft'] else 'ready'}, pushed "
            f"{s['hours']}h ago -> {s['verdict']}{why}")


def candidates(repo, setup):
    """The open pull requests AGENT wrote, with those of ADOPTED_PRS."""
    adopted = {int(p.split("#")[1]) for p in
               setup.get("ADOPTED_PRS", "").split(",")
               if p.strip().startswith(f"{repo}#")}
    return [p for p in pr_status.get(repo, "pulls?state=open")
            if p["user"]["login"] == setup["AGENT"] or p["number"] in adopted]


def sweep(repo, setup, now, quiet, path=FOLDERS):
    """Every candidate measured, oldest first; an unread one says n/a."""
    info = pr_status.request(f"{pr_status.API}/repos/{repo}")
    if info is None:
        raise pr_status.Unread("HTTP 404")
    default = info["default_branch"]
    owned = folder(repo, setup["AGENT"], default, path)
    if not owned:
        raise pr_status.Unread(f"{setup['AGENT']} owns no folder")

    def one(pull):
        try:
            s = measure(repo, pull, owned, default, setup, now)
            if "verdict" not in s:
                s["verdict"], s["reasons"] = verdict(s, quiet)
        except pr_status.Unread as error:
            s = {"pr": f"{repo}#{pull['number']}", "sha": pull["head"]["sha"],
                 "branch": pull["head"]["ref"], "title": pull["title"],
                 "verdict": "n/a", "reasons": [str(error)]}
        return s
    pulls = sorted(candidates(repo, setup), key=lambda p: p["number"])
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        return list(pool.map(one, pulls))


def main(arguments):
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--quiet", type=int, default=24)
    parser.add_argument("--folders", default=FOLDERS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--config", default=os.environ.get(
        "AGENTS_CONFIG") or "config.env")
    args = parser.parse_args(arguments)
    try:
        setup = pr_status.config(args.config)
        setup["AGENT"], setup["USER"]  # pylint: disable=pointless-statement
    except (OSError, ValueError, KeyError) as error:
        parser.error(f"config.env: {error}")
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        rows = sweep(args.repo, setup, now, args.quiet, args.folders)
    except pr_status.Unread as error:
        print(f"{args.repo} n/a ({error})")
        return 2
    for s in rows:
        print(json.dumps(s) if args.json else line(s))
    verdicts = {s["verdict"] for s in rows}
    if "n/a" in verdicts:
        return 2
    return 1 if verdicts & {"ask", "blocked"} else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
