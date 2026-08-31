#!/usr/bin/env python3
"""Sweep open PRs and issues for USER signal the pipeline has not acted on:
bodies and threads where USER spoke last, APPROVE_EMOJI reacts from USER, the
issues closed inside the window, MEMORY_REPO's open-PR count and the state of
each AGENT-owned `TODO.md`. A no-number WORK_REPO sweep also prints the live
default-branch SHA and complete open AGENT-owned PR inventory. A finding is marked 👀
when the pipeline has reacted
to say it received it. config.env is the ground truth for USER, the repos
and the emoji; AGENTS.md's rules say what to do with a finding.

Usage: sweep.py [--since <ISO8601 UTC, e.g. 2026-08-18T00:00:00Z>] <owner/repo>
                [number...]
       # no numbers: every open PR and issue; --since windows the closes
       # and quiets a question the pipeline already 👀'd
Exit 0 and "clean" on a clean sweep, exit 1 with one line per finding. Open
`TODO.md` boxes are printed as context and do not make the sweep dirty.
Exit 2 when GitHub access prevents the sweep: that is neither clean nor a finding.
"""
import base64
import datetime
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zoneinfo

CONFIG = pathlib.Path(__file__).parents[3] / "config.env"
GATE = "not enabled for this session"
BOX = re.compile(r"^\s*[-*] \[([^]]*)\]")
CLAIM = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?"
                   r"(?:Z|[+-]\d{2}:?\d{2})?)?")
STALE = datetime.timedelta(hours=12)
WORK_STATE = re.compile(
    r"^<!-- work-state repo=(\S+) branch=(\S+) sha=([0-9a-f]{7,64}) "
    r"owned=(none|\d+(?:,\d+)*) -->$", re.MULTILINE)
RECEIPT = re.compile(
    r"^<!-- routine-receipt:(\d{4}-\d{2}-\d{2}):(evening|birdsong):"
    r"([A-Za-z0-9._-]+) -->$",
    re.MULTILINE)
RECEIPT_STATUS = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?status\s*:(?:\*\*)?\s*"
    r"`?(started|ran|idle|failed)`?\s*$",
    re.IGNORECASE | re.MULTILINE)
RECEIPT_FIELDS = (
    "Routine", "Date", "Run-ID", "Trigger", "Scheduled", "Started",
    "Finished", "Status", "Eligible", "Selected", "Completed", "Support",
    "Blockers", "Covered-through", "Turn")
START_PENDING = (
    "Finished", "Eligible", "Selected", "Completed", "Support", "Blockers",
    "Covered-through", "Turn")


class NoAccess(Exception):
    """The session cannot read repository-scoped GitHub state."""


def config(path):
    """config.env as a dict, so that the pipeline is configured in one place
    and this script hard-codes no repo and no agent. A value is everything
    after the first `=`; WORK_REPOS is a comma-separated list and ADOPTED_PRS
    space-separated `repo:number,number` entries. A line carrying no `=`
    raises rather than parsing to a key nothing will look up, and a key the
    file does not set is absent, so a caller reading it raises too."""
    setup = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if line.strip() and (not separator or not key.strip()):
            raise ValueError(f"config.env: no key in {line!r}")
        if line.strip():
            setup[key.strip()] = value.strip()
    if "WORK_REPOS" in setup:
        setup["WORK_REPOS"] = setup["WORK_REPOS"].split(",")
    if "ADOPTED_PRS" in setup:
        setup["ADOPTED_PRS"] = {
            repo: [int(number) for number in numbers.split(",") if number]
            for entry in setup["ADOPTED_PRS"].split()
            for repo, _, numbers in [entry.partition(":")]}
    return setup


def get(repo, path):
    """A GitHub REST resource, every page of a listing. A page holds 100 and
    `discopy/discopy` had 153 open items the day this stopped reading one page:
    the tail is the oldest, so a 🚀 on an old issue was invisible for good.
    Unauthenticated GETs work on public repos but are rate-limited to 60/hr;
    GITHUB_TOKEN or GH_TOKEN is used when set."""
    results, page = [], 1
    while True:
        resource = f"/{path}" if path else ""
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repo}{resource}"
            + ("&" if "?" in path else "?") + f"per_page=100&page={page}",
            headers={"User-Agent": "sweep",
                     "Accept": "application/vnd.github+json"})
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request) as response:
                items = json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace").strip()
            if error.code == 403 and GATE in detail.lower():
                raise NoAccess(detail) from None
            raise
        if not isinstance(items, list):  # a single issue, comment or user
            return items
        results += items
        if len(items) < 100:
            return results
        page += 1


def review_comments(repo, number):
    """The pulls/ endpoints reject plain issues, which the sweep also covers."""
    try:
        return get(repo, f"pulls/{number}/comments")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return []
        raise


def reactors(repo, kind, target, emoji, cache):
    """Who reacted with `emoji` on a body or comment, and when. The counts come
    with the target, so only the ones carrying it cost a request, and the
    listing is cached since both emojis are read off the same one."""
    if not target["reactions"][emoji]:
        return []
    if kind not in cache:
        cache[kind] = get(repo, kind)
    return [reaction for reaction in cache[kind] if reaction["content"] == emoji]


def closed_since(repo, since):
    """The issues closed inside the window, with why and by whom. USER answers
    some questions by closing the issue, which leaves no thread to read and no
    open item to walk. One listing per repo, which carries the closer as well
    as the reason; without a window there is no delta, hence nothing."""
    for issue in get(repo, f"issues?state=closed&since={since}") if since else []:
        if "pull_request" in issue or issue["closed_at"] < since:
            continue
        closer = issue.get("closed_by") or {}
        reason = f" {issue['state_reason']}" if issue["state_reason"] else ""
        yield (f"#{issue['number']} closed{reason} by "
               f"{closer.get('login', 'unknown')}: " + issue["html_url"])


def approved(repo, kind, target, setup, cache):
    """Whether USER's APPROVE_EMOJI is on the target. No `since`: a react has no
    answered state, so a window hides a live approval as readily as an old one,
    and every approval on a swept target is reported whatever its age."""
    return any(
        reaction["user"]["login"] == setup["USER"]
        for reaction in reactors(
            repo, kind, target, setup["APPROVE_EMOJI"], cache))


def seen(repo, kind, target, setup, cache):
    """" 👀" when the pipeline has reacted to say it received the instruction,
    "" when nothing has: a flag alone cannot tell the two apart. No `since` —
    an old 👀 still says received."""
    return " 👀" if any(
        reaction["user"]["login"] != setup["USER"]
        for reaction in reactors(repo, kind, target, "eyes", cache)) else ""


def answered(comment, setup):
    """Whether anyone but USER wrote this, AGENT_FOOTER deciding for the ones an
    agent posted from USER's account. Bodies are read for that line only, and
    an issue opened with no description has `None` for one."""
    return (comment["user"]["login"] != setup["USER"]
            or setup["AGENT_FOOTER"]
            in ((comment["body"] or "").strip().splitlines() or [""])[-1])


def asking(repo, kind, target, setup, since, cache):
    """The 👀 flag when `target` is a question of USER's still waiting on us,
    `None` when it is not: either somebody answered it, or the pipeline reacted
    👀 to say it is in hand and `since` puts it before the window. Unanswered is
    a condition rather than an event, so the window never hides one on its own —
    a sweep with no `--since` reports every last question, and a 👀 is what
    quiets an old one."""
    if answered(target, setup):
        return None
    flag = seen(repo, kind, target, setup, cache)
    return None if flag and target["created_at"] < since else flag


def pull_state(pull):
    """One stable state label for the memory inventory."""
    return "merged" if pull.get("merged_at") else pull["state"]


def pull_line(pull):
    """The fields needed to discover evidence on a non-main memory head."""
    head = pull["head"]
    return (f"#{pull['number']} {pull_state(pull)} {pull['updated_at']} "
            f"{head['ref']}@{head['sha']}: {pull['title']} "
            f"{pull['html_url']}")


def receipt_status(body):
    """The last protocol status in a receipt body, or ``None`` when absent.
    Restricting this to the four statuses defined by AGENTS.md keeps prose such
    as ``status: completed`` from becoming lifecycle evidence by accident."""
    statuses = RECEIPT_STATUS.findall(body or "")
    return statuses[-1].lower() if statuses else None


def receipt_values(body):
    """Canonical receipt fields, preserving duplicates for validation."""
    values = {}
    for line in (body or "").splitlines():
        key, separator, value = line.partition(":")
        if separator and key in RECEIPT_FIELDS:
            values.setdefault(key, []).append(value.strip())
    return values


def valid_receipt(body, day, routine, run_id):
    """Whether one marked comment has the complete canonical current shape."""
    values = receipt_values(body)
    if any(len(values.get(field, [])) != 1 for field in RECEIPT_FIELDS):
        return False
    status = receipt_status(body)
    if not (values["Routine"][0].lower() == routine
            and values["Date"][0] == day
            and values["Run-ID"][0] == run_id
            and values["Trigger"][0] in ("scheduled", "manual", "unknown")
            and status is not None
            and values["Status"][0].lower() == status
            and all(values[field][0] for field in RECEIPT_FIELDS)):
        return False
    if status == "started":
        return all(values[field][0].lower() == "pending"
                   for field in START_PENDING)
    return all(values[field][0].lower() != "pending"
               for field in RECEIPT_FIELDS)


def routine_receipts(repo, pulls):
    """Canonical receipt markers found in the inventoried memory PR comments.
    The comment is edited in place as a run progresses, so a marker appearing
    in two comments is a duplicate rather than a second lifecycle event."""
    receipts = {}
    for pull in pulls:
        for comment in get(repo, f"issues/{pull['number']}/comments"):
            body = comment.get("body") or ""
            for day, routine, run_id in RECEIPT.findall(body):
                values = receipt_values(body)
                valid = valid_receipt(body, day, routine, run_id)
                receipts.setdefault((day, routine, run_id), []).append({
                    "pull": pull["number"],
                    "status": receipt_status(body) if valid else "unknown",
                    "trigger": (values.get("Trigger") or ["unknown"])[-1],
                    "covered_through": (
                        values.get("Covered-through") or ["unknown"])[-1],
                    "valid": valid,
                    "updated_at": comment.get("updated_at", ""),
                    "url": comment.get("html_url", pull["html_url"]),
                })
    return receipts


def memory(repo, since):
    """MEMORY_REPO holds one open PR per day, checked whatever the window since
    it is an invariant rather than a delta. Several open at once is USER not
    having merged the past days, which is theirs and no finding of ours; two
    under one title is a day written twice, which is ours. The count and the
    URLs are printed either way, so a turn sees what is waiting to be merged
    without the sweep calling it dirty."""
    pulls = get(repo, "pulls?state=all&sort=updated&direction=desc")
    open_prs = [pull for pull in pulls if pull["state"] == "open"]
    recent = [pull for pull in pulls
              if since and pull["state"] != "open" and pull["updated_at"] >= since]
    receipts = routine_receipts(repo, open_prs + recent)
    receipt_lines = []
    for (day, routine, run_id), copies in sorted(receipts.items()):
        latest = max(copies, key=lambda receipt: receipt["updated_at"])
        status = latest["status"] if len(copies) == 1 else "unknown"
        receipt_lines.append(
            f"\n  receipt {day} {routine} run={run_id} trigger={latest['trigger']} "
            f"status={status} covered-through={latest['covered_through']} "
            f"on #{latest['pull']}: {latest['url']}")
    print(f"{repo}: {len(open_prs)} open PR(s)"
          + "".join("\n  " + pull_line(pull) for pull in open_prs)
          + ("\nupdated since last sweep:"
             + "".join("\n  " + pull_line(pull) for pull in recent)
             if recent else "")
          + "".join(receipt_lines),
          file=sys.stderr)
    days = {}
    for pull in open_prs:
        days.setdefault(pull["title"], []).append(pull["html_url"])
    findings = [
        f"{repo}: {len(urls)} open PRs titled {title!r}, one a day is the"
        " rule — push to one and close the rest: " + ", ".join(urls)
        for title, urls in days.items() if len(urls) > 1]
    findings += [
        f"{repo}: duplicate routine receipt {day} {routine} run={run_id}: "
        + ", ".join(receipt["url"] for receipt in copies)
        for (day, routine, run_id), copies in sorted(receipts.items())
        if len(copies) > 1]
    findings += [
        f"{repo}: malformed routine receipt {day} {routine} run={run_id}: "
        + ", ".join(receipt["url"] for receipt in copies if not receipt["valid"])
        for (day, routine, run_id), copies in sorted(receipts.items())
        if any(not receipt["valid"] for receipt in copies)]
    started = {}
    for (day, routine, run_id), copies in receipts.items():
        if (len(copies) == 1 and copies[0]["valid"]
                and copies[0]["status"] == "started"):
            started.setdefault((day, routine), []).append(run_id)
    findings += [
        f"{repo}: conflicting started receipts {day} {routine}: "
        + ", ".join(sorted(run_ids))
        for (day, routine), run_ids in sorted(started.items())
        if len(run_ids) > 1]
    return findings


def default_branch(repo, cache):
    """The repository's configured default branch, cached per sweep."""
    if "default_branch" not in cache:
        cache["default_branch"] = get(repo, "")["default_branch"]
    return cache["default_branch"]


def work_state(repo, setup, cache):
    """Live invariants the board must re-derive rather than carry forward."""
    branch = default_branch(repo, cache)
    sha = get(repo, "commits/" + urllib.parse.quote(branch, safe=""))["sha"]
    adopted = set(setup.get("ADOPTED_PRS", {}).get(repo, []))
    numbers = sorted(
        number for number, pull in heads(repo, cache).items()
        if pull["user"]["login"] == setup["AGENT"] or number in adopted)
    owned = ",".join(str(number) for number in numbers) or "none"
    marker = (f"<!-- work-state repo={repo} branch={branch} sha={sha} "
              f"owned={owned} -->")
    listed = ",".join(f"#{number}" for number in numbers) or "none"
    return marker + f"\n{repo}: live {branch} {sha}; open AGENT-owned PRs {listed}"


def board_state(repo, setup, marker, day=None):
    """Compare live work state with today's open memory head's board.

    No open memory PR means no board is currently being rewritten, so the live
    marker remains context rather than a finding. Once a day PR exists, an
    exact marker makes drift deterministic instead of a prose comparison.
    """
    pulls = get(setup["MEMORY_REPO"], "pulls?state=open")
    day = day or datetime.datetime.now(zoneinfo.ZoneInfo(
        setup["ROUTINE_TIMEZONE"])).date().isoformat()
    matches = [pull for pull in pulls if pull["title"] == day]
    if not matches:
        return []
    if len(matches) > 1:
        return [f"{setup['MEMORY_REPO']}: {len(matches)} open {day} boards; "
                "cannot verify work-state marker"]
    current = matches[0]
    text = contents(setup["MEMORY_REPO"], "README.md", current["head"]["sha"])
    markers = [match.group(0) for match in WORK_STATE.finditer(text or "")
               if match.group(1) == repo]
    if markers == [marker]:
        return []
    reason = "missing" if not markers else "duplicate" if len(markers) > 1 else "stale"
    return [
        f"{setup['MEMORY_REPO']}#{current['number']}: {reason} board marker for {repo}; "
        f"replace with {marker}: {current['html_url']}"]


def heads(repo, cache):
    """Every open pull request by number. `TODO.md` is read off the head
    commit, which the listing already carries, so the whole repo costs one
    request rather than one per pull request."""
    if "heads" not in cache:
        cache["heads"] = {pull["number"]: pull
                          for pull in get(repo, "pulls?state=open")}
    return cache["heads"]


def contents(repo, path, ref):
    """A file at one commit, `None` when that commit does not carry it: a
    missing `TODO.md` is a finding here rather than an error. Undecodable bytes
    are replaced rather than raised, since one unreadable file would otherwise
    abort the whole sweep. `validate=True` is wrong here — GitHub wraps the
    base64 it serves, which the strict decoder rejects."""
    try:
        blob = get(repo, f"contents/{path}?ref={ref}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    return base64.b64decode(blob["content"]).decode(errors="replace")


def claimed(box):
    """When a `[WIP]` box was claimed, `None` when it carries no readable date.
    Rule 3 stamps `@<SessionID>-<yyyy-MM-dd HH:mm>`, in practice with an offset
    or a `Z` and sometimes a range, so the first date on the line wins and a
    naive one is read as UTC."""
    stamp = CLAIM.search(box)
    if not stamp:
        return None
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2",
                  stamp.group().replace(" ", "T").replace("Z", "+00:00"))
    try:
        when = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(
        tzinfo=datetime.timezone.utc)


def cleared(repo, head, cache):
    """Whether this branch carried a `TODO.md` and deleted it, which is what
    clears the merge gate. Both cases read as missing at the head, and the
    diff cannot tell them apart either: adding a file and deleting it again
    nets out to nothing. The branch's own commits touching the path do, once
    the ones it inherits from the repository's default branch are taken out.
    Asked only of a branch already known to have no `TODO.md`."""
    if "cleared" not in cache:
        branch = urllib.parse.quote(default_branch(repo, cache), safe="")
        cache["cleared"] = {commit["sha"] for commit in get(
            repo, f"commits?sha={branch}&path=TODO.md")}
    return any(commit["sha"] not in cache["cleared"] for commit in get(
        repo, f"commits?sha={head}&path=TODO.md"))


def elapsed(age):
    """An age in whole hours, in days once there are two of them: the window
    is twelve hours and the claims that break it run to weeks."""
    hours = int(age.total_seconds() // 3600)
    return f"{hours // 24} days" if hours >= 48 else f"{hours} hours"


def owned(repo, number, body, setup):
    """Whether the pipeline is answerable for this pull request: AGENT opened
    it or ADOPTED_PRS lists it, the same test the board and the scans use.
    Nobody else's branch owes us a `TODO.md`, and neither does one in
    DESIRE_REPO or MEMORY_REPO — the rule binds where the work happens."""
    return "pull_request" in body and repo in setup["WORK_REPOS"] and (
        body["user"]["login"] == setup["AGENT"]
        or number in setup.get("ADOPTED_PRS", {}).get(repo, []))


def todo(repo, number, body, setup, cache):
    """The `TODO.md` findings on one AGENT-owned pull request. Its boxes are
    the mutex between parallel agents and deleting the file is what clears the
    merge gate, so it is the one file that says whether a pull request is
    finished and nothing else in the sweep reads it. Open boxes are printed
    the way MEMORY_REPO's PR count is — work left is the normal state of a
    branch, not a finding — while a claim past Rule 3's twelve hours and a
    branch that never carried the file are reported."""
    if not owned(repo, number, body, setup):
        return []
    head = (heads(repo, cache).get(number)
            or get(repo, f"pulls/{number}"))["head"]["sha"]
    text = contents(repo, "TODO.md", head)
    if text is None:
        return [] if cleared(repo, head, cache) else [
            f"#{number} never carried a TODO.md, so it cannot reach sign-off: "
            + body["html_url"]]
    boxes = [(mark.group(1).strip(), line) for line in text.splitlines()
             for mark in [BOX.match(line)] if mark]
    if opened := [line for mark, line in boxes if not mark]:
        print(f"{repo}#{number}: {len(opened)} of {len(boxes)} TODO.md"
              " point(s) open", file=sys.stderr)
    findings = []
    for mark, line in boxes:
        if "WIP" not in mark.upper():
            continue
        when = claimed(line)
        age = None if when is None else (
            datetime.datetime.now(datetime.timezone.utc) - when)
        if age is not None and age < STALE:
            continue
        findings.append(
            f"#{number} stale [WIP] claim, "
            + ("no readable date" if age is None else
               f"{when:%Y-%m-%d} ({elapsed(age)} old)")
            + ", reclaim it: " + body["html_url"])
    return findings


def item(repo, number, setup, since, cache):
    """The findings on one PR or issue: USER's APPROVE_EMOJI on the body or on
    any comment, and every thread where USER spoke last. GitHub splits comments
    across two endpoints, review comments threaded by in_reply_to_id and the
    conversation tab flat; both are swept, and so are the bodies. A body USER
    wrote is the thread when nothing else was said on it, which is the shape a
    standing order arrives in; once anyone comments, that thread's last word
    answers for it and the body would only report it twice. `asking` decides
    which of the two are still waiting on us."""
    findings, threads, body = [], {}, get(repo, f"issues/{number}")
    kind = f"issues/{number}/reactions"
    if approved(repo, kind, body, setup, cache):
        findings.append(
            f"#{number} {setup['APPROVE_EMOJI']} from {setup['USER']} on the"
            f" body: {body['html_url']}" + seen(repo, kind, body, setup, cache))
    comments = [(comment, comment.get("in_reply_to_id", comment["id"]), "pulls")
                for comment in review_comments(repo, number)]
    comments += [(comment, number, "issues")
                 for comment in get(repo, f"issues/{number}/comments")]
    for comment, thread, endpoint in comments:
        threads.setdefault((endpoint, thread), []).append(comment)
        kind = f"{endpoint}/comments/{comment['id']}/reactions"
        if approved(repo, kind, comment, setup, cache):
            findings.append(
                f"#{number} {setup['APPROVE_EMOJI']} from {setup['USER']}:"
                f" {comment['html_url']}"
                + seen(repo, kind, comment, setup, cache))
    for (endpoint, _), thread in threads.items():
        asked = thread[-1]  # both endpoints list oldest first
        kind = f"{endpoint}/comments/{asked['id']}/reactions"
        flag = asking(repo, kind, asked, setup, since, cache)
        if flag is not None:
            findings.append(
                f"#{number} unanswered {setup['USER']} comment:"
                f" {asked['html_url']}" + flag)
    kind = f"issues/{number}/reactions"
    flag = None if threads else asking(repo, kind, body, setup, since, cache)
    if flag is not None:
        findings.append(
            f"#{number} unanswered {setup['USER']}"
            f" {'pull request' if 'pull_request' in body else 'issue'}:"
            f" {body['html_url']}" + flag)
    return findings + todo(repo, number, body, setup, cache)


def sweep(repo, numbers, since, setup):
    """One line per finding, empty when the sweep is clean."""
    cache, findings = {}, []
    if repo == setup["MEMORY_REPO"] and not numbers:
        findings += memory(repo, since)
    if repo in setup["WORK_REPOS"] and not numbers:
        state = work_state(repo, setup, cache)
        print(state, file=sys.stderr)
        findings += board_state(repo, setup, state.splitlines()[0])
    if not numbers:
        findings += closed_since(repo, since)
        numbers = sorted({
            issue["number"] for issue in get(repo, "issues?state=open")})
    for number in numbers:
        findings += item(repo, number, setup, since, cache)
    return findings


def main(arguments):
    since = ""  # ISO 8601 UTC sorts lexicographically, so "" is the epoch
    if arguments and arguments[0] == "--since":
        _, since, *arguments = arguments
    try:
        findings = sweep(arguments[0], [int(n) for n in arguments[1:]], since,
                         config(CONFIG))
    except NoAccess as error:
        print(f"cannot sweep {arguments[0]}: GitHub access unavailable; not clean\n{error}",
              file=sys.stderr)
        return 2
    except urllib.error.HTTPError as error:
        print(f"cannot sweep {arguments[0]}: GitHub HTTP {error.code} {error.reason}; not clean",
              file=sys.stderr)
        return 2
    except urllib.error.URLError as error:
        print(f"cannot sweep {arguments[0]}: GitHub transport failed: {error.reason}; not clean",
              file=sys.stderr)
        return 2
    print("\n".join(findings) if findings else "clean", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
