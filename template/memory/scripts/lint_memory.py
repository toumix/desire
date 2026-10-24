#!/usr/bin/env python3
"""Lint memory conventions; see docs/lint.md for rules and exit codes."""
import argparse
from collections import Counter
from datetime import date
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
from urllib.error import HTTPError
from urllib.parse import unquote, urldefrag, urlsplit
from urllib.request import Request, urlopen

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sweep", ROOT / ".agents/skills/sweep/sweep.py")
sweep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sweep)
MD = MarkdownIt("commonmark", {"html": True})
FIELDS = ("whose", "does", "needs", "touches", "blocks")
FIELD = re.compile(r"^- \*\*(\w+)\*\*\s*(.*)")
LOG = re.compile(r"^- \*\*(\d{4}-\d{2}-\d{2})(.*?)\*\*\s*(.*)")
ITEM_URL = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/(?:issues|pull)/(\d+)")


def valid_date(value):
    try:
        return date.fromisoformat(value) <= date.today()
    except ValueError:
        return False


def prose(text):
    """Mask fenced/indented code, preserving source line numbers."""
    lines = text.splitlines()
    for token in MD.parse(text):
        if token.type in {"fence", "code_block"}:
            for index in range(*token.map):
                lines[index] = ""
    return lines


def links(text):
    """CommonMark inline/reference links, images and autolinks; skip code."""
    for token in MD.parse(text):
        if token.type != "inline":
            continue
        for child in token.children or []:
            key = {"link_open": "href", "image": "src"}.get(child.type)
            if key:
                yield token.map[0] + 1, child.attrGet(key)
    # Bare URLs in notes are also evidence, even without Markdown markup.
    for number, line in enumerate(prose(text), 1):
        line = re.sub(r"`+[^`]*`+", "", line)
        for match in re.finditer(r"https?://[^\s<>\]\)]+", line):
            yield number, match.group().rstrip(".,;:!\"'")


def anchors(text):
    result, counts = set(), Counter()
    tokens = MD.parse(text)
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        title = "".join(child.content for child in tokens[index + 1].children
                        if child.type in {"text", "code_inline"})
        slug = "".join(c for c in title.lower()
                       if c in "-_ " or unicodedata.category(c)[0] in "LNM")
        slug = slug.replace(" ", "-")
        suffix = f"-{counts[slug]}" if counts[slug] else ""
        counts[slug] += 1
        result.add(slug + suffix)
    result.update(re.findall(r'\b(?:id|name)=["\']([^"\']+)["\']', text))
    return result


class Audit:
    def __init__(self, root, setup):
        self.root, self.setup = root.resolve(), setup
        self.findings, self.incomplete = [], []
        self.texts, self.notes, self.urls = {}, {}, {}
        self.repos = {}
        if not setup.get("AGENT") or not setup.get("WORK_REPOS"):
            raise ValueError("config.env must set AGENT and nonempty WORK_REPOS")
        for repo in setup["WORK_REPOS"]:
            if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
                raise ValueError(f"invalid WORK_REPOS entry: {repo!r}")
            name = repo.split("/")[-1]
            if name in self.repos and self.repos[name] != repo:
                raise ValueError(f"ambiguous WORK directory {name}: {self.repos[name]}, {repo}")
            self.repos[name] = repo

    def add(self, path, line, rule, message):
        self.findings.append(f"{path}:{line}: {rule}: {message}")

    def local(self):
        paths = sorted(self.root.rglob("*.md"))
        for path in paths:
            relative = path.relative_to(self.root)
            if any(part.startswith(".") for part in relative.parts[:-1]) and relative.parts[0] != ".github":
                continue
            text = path.read_text(encoding="utf-8")
            self.texts[relative] = text
            lines = prose(text)
            for number, line in enumerate(lines, 1):
                if re.match(r"^(<<<<<<< |=======$|>>>>>>> )", line):
                    self.add(relative, number, "merge-markers", "unresolved merge conflict")
            if relative == Path("README.md") and len(text.splitlines()) >= 200:
                self.add(relative, 1, "board-length", "board must stay under 200 lines")
            if relative.parts[0] == "WORK" and relative != Path("WORK/TEMPLATE.md"):
                self.note(relative, lines)
            for number, url in set(links(text)):
                self.link(relative, number, url)

    def note(self, path, lines):
        if len(path.parts) != 3 or not re.fullmatch(r"[1-9]\d*\.md", path.name):
            self.add(path, 1, "note-path", "expected WORK/<repo>/<positive number>.md")
            return
        name, number = path.parts[1], int(path.stem)
        if name not in self.repos:
            self.add(path, 1, "note-repo", "repository is absent from WORK_REPOS")
        expected = rf"# {re.escape(name)}#{number} — \S"
        if not lines or not re.match(expected, lines[0]):
            self.add(path, 1, "note-title", f"expected '# {name}#{number} — <summary>'")
        fields = [(i, m.group(1), m.group(2)) for i, line in enumerate(lines, 1)
                  if (m := FIELD.match(line)) and not LOG.match(line)]
        if [key for _, key, _ in fields] != list(FIELDS):
            self.add(path, 1, "note-fields", "expected exactly whose, does, needs, touches, blocks in order; live state belongs on GitHub")
        for i, key, value in fields:
            if not value.strip():
                self.add(path, i, "empty-field", f"{key} needs an explicit answer, including 'none' or 'unknown'")
        whose = next(((i, value) for i, key, value in fields if key == "whose"), (1, ""))
        read = re.search(r"\bread (\d{4}-\d{2}-\d{2})\b", whose[1])
        day = read.group(1) if read else None
        if day is None or not valid_date(day):
            self.add(path, whose[0], "read-date", "whose must carry a valid, non-future 'read YYYY-MM-DD'")
            day = None
        # Legacy notes still get freshness checks while their shape is flagged.
        legacy = sweep.READ.search("\n".join(lines))
        sync_day = day or (legacy.group(1) if legacy and valid_date(legacy.group(1)) else None)
        self.notes[(name, number)] = (path, sync_day)
        logs = [(i, m) for i, line in enumerate(lines, 1) if (m := LOG.match(line))]
        if not 1 <= len(logs) <= 5:
            self.add(path, 1, "note-log", f"keep the last 1–5 turns (found {len(logs)})")
        dates = []
        for i, match in logs:
            dates.append(match.group(1))
            if not valid_date(match.group(1)) or not match.group(2).strip() or not match.group(3).strip():
                self.add(path, i, "log-entry", "expected a valid date, phase/person, and what changed")
        if dates != sorted(dates, reverse=True):
            self.add(path, 1, "log-order", "turn log must be newest first")

    def link(self, path, line, url):
        parsed = urlsplit(url)
        if parsed.scheme in {"http", "https"}:
            self.urls.setdefault(urldefrag(url)[0], (path, line))
            return
        if parsed.scheme in {"mailto", "tel"}:
            return
        if parsed.scheme or parsed.netloc:
            self.add(path, line, "link-scheme", f"unsupported link: {url}")
            return
        target = (self.root / path.parent / unquote(parsed.path)).resolve() if parsed.path else self.root / path
        if not target.is_relative_to(self.root):
            self.add(path, line, "local-link", f"link leaves the repo: {url}")
        elif not target.exists():
            self.add(path, line, "local-link", f"missing target: {url}")
        elif parsed.fragment and target.suffix == ".md" and unquote(parsed.fragment) not in anchors(target.read_text()):
            self.add(path, line, "local-anchor", f"missing heading/anchor: {url}")

    def github(self, get):
        """Full open-item lists: closed notes, missing required notes, freshness."""
        all_texts = [text for path, text in self.texts.items() if path.parts[0] == "WORK"]
        for name, repo in self.repos.items():
            try:
                items = get(repo, "issues?state=open")
            except (OSError, ValueError) as error:
                self.incomplete.append(f"{repo}: GitHub unreadable: {error}")
                continue
            opened = {item["number"]: item for item in items}
            texts = [text for path, text in self.texts.items() if path.parts[:2] == ("WORK", name)]
            required = sweep.required(repo, items, texts, self.setup)
            # References across directories also require notes, including full URLs.
            for text in all_texts:
                required |= {int(n) for prefix, n in sweep.CITE.findall(text)
                             if prefix.strip("/") in {name, repo} and int(n) in opened}
                required |= {int(n) for owner_repo, n in ITEM_URL.findall(text)
                             if owner_repo == repo and int(n) in opened}
            for number in sorted(required):
                if (name, number) not in self.notes:
                    self.add(f"WORK/{name}/{number}.md", 1, "missing-note", f"open authored/adopted/cited item requires a note: {opened[number]['html_url']}")
            for (note_repo, number), (path, day) in self.notes.items():
                if note_repo != name:
                    continue
                if number not in opened:
                    self.add(path, 1, "closed-note", "item is no longer open; delete its note after checking GitHub")
                elif day is not None and day < opened[number]["updated_at"][:10]:
                    self.add(path, 1, "stale-note", f"read {day}; item updated {opened[number]['updated_at']}; re-read before updating the date")

    def external(self, check):
        for url, (path, line) in sorted(self.urls.items()):
            try:
                check(url)
            except HTTPError as error:
                if error.code in {404, 410}:
                    self.add(path, line, "external-link", f"HTTP {error.code}: {url} (private targets may require access)")
                else:
                    self.incomplete.append(f"{path}:{line}: {url}: HTTP {error.code}; link could not be verified")
            except (OSError, ValueError) as error:
                self.incomplete.append(f"{path}:{line}: {url}: link could not be verified: {error}")


class GitHub:
    """Read-only, bounded requests with pagination; credentials stay on API host."""
    def __init__(self, timeout):
        self.timeout = timeout

    def get(self, repo, path):
        result, page = [], 1
        while True:
            url = f"https://api.github.com/repos/{repo}/{path}"
            url += ("&" if "?" in url else "?") + f"per_page=100&page={page}"
            headers = {"User-Agent": "memory-lint", "Accept": "application/vnd.github+json"}
            token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
            request = Request(url, headers=headers)
            if token:
                request.add_unredirected_header("Authorization", f"Bearer {token}")
            with urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
            if not isinstance(data, list):
                raise ValueError("expected a GitHub listing")
            result.extend(data)
            if len(data) < 100:
                return result
            page += 1

    def check(self, url):
        # No GitHub token is sent to arbitrary URLs (including redirects).
        request = Request(url, headers={"User-Agent": "memory-lint"}, method="HEAD")
        try:
            with urlopen(request, timeout=self.timeout):
                return
        except HTTPError as error:
            if error.code not in {405, 501}:
                raise
        with urlopen(Request(url, headers={"User-Agent": "memory-lint"}), timeout=self.timeout):
            return


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--github", action="store_true", help="compare WORK with live GitHub open items")
    parser.add_argument("--external-links", action="store_true", help="check HTTP(S) URLs")
    parser.add_argument("--timeout", type=float, default=10, help="seconds per network request")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        setup = sweep.config(args.root / "config.env")
        audit = Audit(args.root, setup)
        audit.local()
        client = GitHub(args.timeout)
        if args.github:
            audit.github(client.get)
        if args.external_links:
            audit.external(client.check)
    except (OSError, ValueError, KeyError) as error:
        print(f"incomplete: {error}", file=sys.stderr)
        return 2
    for finding in audit.findings:
        print(finding)
    for failure in audit.incomplete:
        print(f"incomplete: {failure}", file=sys.stderr)
    modes = "local" + (", GitHub" if args.github else "") + (", external links" if args.external_links else "")
    print(f"Checked {modes}: {len(audit.findings)} finding(s), {len(audit.incomplete)} incomplete check(s)")
    return 2 if audit.incomplete else 1 if audit.findings else 0


if __name__ == "__main__":
    sys.exit(main())
