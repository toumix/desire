import contextlib
import io
import unittest
import urllib.error
from unittest.mock import patch

import sweep


def receipt(day, routine, status, run_id="run-1"):
    pending = status == "started"
    return "\n".join([
        f"<!-- routine-receipt:{day}:{routine}:{run_id} -->",
        f"Routine: {routine.title()}",
        f"Date: {day}",
        f"Run-ID: {run_id}",
        "Trigger: scheduled",
        "Scheduled: 2026-08-31T00:05:00Z",
        "Started: 2026-08-31T00:05:01Z",
        "Finished: " + ("pending" if pending else "2026-08-31T01:00:00Z"),
        f"Status: {status}",
        "Eligible: " + ("pending" if pending else "none"),
        "Selected: " + ("pending" if pending else "none"),
        "Completed: " + ("pending" if pending else "none"),
        "Support: " + ("pending" if pending else "none"),
        "Blockers: " + ("pending" if pending else "none"),
        "Covered-through: " + (
            "pending" if pending else "2026-08-31T00:59:00Z"),
        "Turn: " + ("pending" if pending else "https://example.test/turn"),
    ])


class SweepEvidenceTest(unittest.TestCase):
    def test_config_records_expected_routine_days(self):
        self.assertEqual(
            sweep.config(sweep.CONFIG)["ROUTINE_DAYS"],
            "Mon,Tue,Wed,Thu,Fri")
        self.assertEqual(
            sweep.config(sweep.CONFIG)["ROUTINE_TIMEZONE"],
            "Europe/Paris")

    @patch("sweep.get")
    def test_work_state_lists_live_default_branch_and_all_owned_heads(self, get):
        get.side_effect = lambda _, path: {
            "": {"default_branch": "trunk"},
            "commits/trunk": {"sha": "abc1234"},
            "pulls?state=open": [
                {"number": 3, "user": {"login": "agent"}},
                {"number": 7, "user": {"login": "other"}},
                {"number": 9, "user": {"login": "other"}},
            ],
        }[path]
        setup = {"AGENT": "agent", "ADOPTED_PRS": {"o/r": [7]}}

        self.assertEqual(
            sweep.work_state("o/r", setup, {}),
            "<!-- work-state repo=o/r branch=trunk sha=abc1234 owned=3,7 -->\n"
            "o/r: live trunk abc1234; open AGENT-owned PRs #3,#7")

    @patch("sweep.contents")
    @patch("sweep.get")
    def test_board_state_accepts_exact_marker_on_todays_head(self, get, contents):
        get.return_value = [
            {
                "number": 8,
                "title": "2026-08-31",
                "html_url": "https://example.test/pull/8",
                "head": {"sha": "memory-head"},
            },
            {
                "number": 9,
                "title": "2026-08-30",
                "html_url": "https://example.test/pull/9",
                "head": {"sha": "other-head"},
            },
        ]
        marker = "<!-- work-state repo=o/r branch=trunk sha=abc1234 owned=3,7 -->"
        contents.return_value = marker

        self.assertEqual(
            sweep.board_state(
                "o/r", {"MEMORY_REPO": "o/memory"}, marker,
                day="2026-08-31"), [])
        contents.assert_called_once_with("o/memory", "README.md", "memory-head")

    @patch("sweep.contents")
    @patch("sweep.get")
    def test_board_state_reports_stale_marker(self, get, contents):
        get.return_value = [{
            "number": 8,
            "title": "2026-08-31",
            "html_url": "https://example.test/pull/8",
            "head": {"sha": "memory-head"},
        }]
        contents.return_value = (
            "<!-- work-state repo=o/r branch=main sha=def5678 owned=3 -->")
        marker = "<!-- work-state repo=o/r branch=trunk sha=abc1234 owned=3,7 -->"

        findings = sweep.board_state(
            "o/r", {"MEMORY_REPO": "o/memory"}, marker,
            day="2026-08-31")

        self.assertEqual(len(findings), 1)
        self.assertIn("stale board marker for o/r", findings[0])
        self.assertIn(marker, findings[0])

    @patch("sweep.get")
    def test_memory_inventory_includes_open_heads_and_recent_closes(self, get):
        def pull(number, state, updated, title, merged=False):
            return {
                "number": number,
                "state": state,
                "updated_at": updated,
                "merged_at": updated if merged else None,
                "title": title,
                "html_url": f"https://example.test/{number}",
                "head": {"ref": f"head-{number}", "sha": f"sha-{number}"},
            }

        pulls = [
            pull(4, "open", "2026-08-31T08:00:00Z", "2026-08-31"),
            pull(3, "closed", "2026-08-31T07:00:00Z", "2026-08-30", merged=True),
            pull(2, "closed", "2026-08-29T07:00:00Z", "2026-08-29"),
        ]
        get.side_effect = lambda _, path: (
            pulls if path == "pulls?state=all&sort=updated&direction=desc" else [])
        output = io.StringIO()

        with contextlib.redirect_stderr(output):
            findings = sweep.memory("o/memory", "2026-08-30T03:00:00Z")

        self.assertEqual(findings, [])
        self.assertIn("#4 open 2026-08-31T08:00:00Z head-4@sha-4", output.getvalue())
        self.assertIn("#3 merged 2026-08-31T07:00:00Z head-3@sha-3", output.getvalue())
        self.assertNotIn("#2 closed", output.getvalue())

    @patch("sweep.get")
    def test_memory_inventory_prints_one_line_for_a_unique_receipt(self, get):
        pull = {
            "number": 4,
            "state": "open",
            "updated_at": "2026-08-31T08:00:00Z",
            "merged_at": None,
            "title": "2026-08-31",
            "html_url": "https://example.test/pull/4",
            "head": {"ref": "head-4", "sha": "sha-4"},
        }
        comment = {
            "body": receipt("2026-08-31", "evening", "ran"),
            "html_url": "https://example.test/pull/4#comment-1",
            "updated_at": "2026-08-31T01:00:00Z",
        }
        get.side_effect = lambda _, path: (
            [pull] if path == "pulls?state=all&sort=updated&direction=desc"
            else [comment])
        output = io.StringIO()

        with contextlib.redirect_stderr(output):
            findings = sweep.memory("o/memory", "")

        self.assertEqual(findings, [])
        line = ("receipt 2026-08-31 evening run=run-1 trigger=scheduled "
                "status=ran")
        self.assertEqual(output.getvalue().count(line), 1)

    @patch("sweep.get")
    def test_memory_inventory_reports_duplicate_receipt_markers(self, get):
        pull = {
            "number": 4,
            "state": "open",
            "updated_at": "2026-08-31T08:00:00Z",
            "merged_at": None,
            "title": "2026-08-31",
            "html_url": "https://example.test/pull/4",
            "head": {"ref": "head-4", "sha": "sha-4"},
        }
        comments = [
            {
                "body": receipt("2026-08-31", "evening", "started"),
                "html_url": "https://example.test/pull/4#comment-1",
                "updated_at": "2026-08-31T00:10:00Z",
            },
            {
                "body": receipt("2026-08-31", "evening", "ran"),
                "html_url": "https://example.test/pull/4#comment-2",
                "updated_at": "2026-08-31T01:00:00Z",
            },
        ]
        get.side_effect = lambda _, path: (
            [pull] if path == "pulls?state=all&sort=updated&direction=desc"
            else comments)
        output = io.StringIO()

        with contextlib.redirect_stderr(output):
            findings = sweep.memory("o/memory", "")

        self.assertEqual(len(findings), 1)
        self.assertIn("duplicate routine receipt 2026-08-31 evening", findings[0])
        line = ("receipt 2026-08-31 evening run=run-1 trigger=scheduled "
                "status=unknown")
        self.assertEqual(output.getvalue().count(line), 1)

    @patch("sweep.get")
    def test_memory_inventory_reports_malformed_receipt(self, get):
        pull = {
            "number": 4,
            "state": "open",
            "updated_at": "2026-08-31T08:00:00Z",
            "merged_at": None,
            "title": "2026-08-31",
            "html_url": "https://example.test/pull/4",
            "head": {"ref": "head-4", "sha": "sha-4"},
        }
        comment = {
            "body": "<!-- routine-receipt:2026-08-31:evening:run-1 -->\nStatus: ran",
            "html_url": "https://example.test/pull/4#comment-1",
            "updated_at": "2026-08-31T01:00:00Z",
        }
        get.side_effect = lambda _, path: (
            [pull] if path == "pulls?state=all&sort=updated&direction=desc"
            else [comment])

        with contextlib.redirect_stderr(io.StringIO()):
            findings = sweep.memory("o/memory", "")

        self.assertEqual(len(findings), 1)
        self.assertIn(
            "malformed routine receipt 2026-08-31 evening run=run-1",
            findings[0])

    @patch("sweep.get")
    def test_same_day_retry_run_ids_are_not_duplicates(self, get):
        pull = {
            "number": 4,
            "state": "open",
            "updated_at": "2026-08-31T08:00:00Z",
            "merged_at": None,
            "title": "2026-08-31",
            "html_url": "https://example.test/pull/4",
            "head": {"ref": "head-4", "sha": "sha-4"},
        }
        comments = [
            {
                "body": receipt("2026-08-31", "evening", "failed", "run-1"),
                "html_url": "https://example.test/pull/4#comment-1",
                "updated_at": "2026-08-31T00:30:00Z",
            },
            {
                "body": receipt("2026-08-31", "evening", "ran", "run-2"),
                "html_url": "https://example.test/pull/4#comment-2",
                "updated_at": "2026-08-31T01:00:00Z",
            },
        ]
        get.side_effect = lambda _, path: (
            [pull] if path == "pulls?state=all&sort=updated&direction=desc"
            else comments)

        with contextlib.redirect_stderr(io.StringIO()):
            findings = sweep.memory("o/memory", "")

        self.assertEqual(findings, [])

    @patch("sweep.get")
    def test_multiple_started_attempts_are_conflicting(self, get):
        pull = {
            "number": 4,
            "state": "open",
            "updated_at": "2026-08-31T08:00:00Z",
            "merged_at": None,
            "title": "2026-08-31",
            "html_url": "https://example.test/pull/4",
            "head": {"ref": "head-4", "sha": "sha-4"},
        }
        comments = [
            {
                "body": receipt("2026-08-31", "evening", "started", "run-1"),
                "html_url": "https://example.test/pull/4#comment-1",
                "updated_at": "2026-08-31T00:10:00Z",
            },
            {
                "body": receipt("2026-08-31", "evening", "started", "run-2"),
                "html_url": "https://example.test/pull/4#comment-2",
                "updated_at": "2026-08-31T00:20:00Z",
            },
        ]
        get.side_effect = lambda _, path: (
            [pull] if path == "pulls?state=all&sort=updated&direction=desc"
            else comments)

        with contextlib.redirect_stderr(io.StringIO()):
            findings = sweep.memory("o/memory", "")

        self.assertEqual(len(findings), 1)
        self.assertIn(
            "conflicting started receipts 2026-08-31 evening: run-1, run-2",
            findings[0])

    def test_receipt_status_extracts_only_protocol_statuses(self):
        for status in ("started", "ran", "idle", "failed"):
            with self.subTest(status=status):
                self.assertEqual(
                    sweep.receipt_status(f"**Status:** `{status.upper()}`"),
                    status)
        self.assertIsNone(sweep.receipt_status("status: completed"))

    def test_receipt_lifecycle_requires_pending_only_at_start(self):
        started = receipt("2026-08-31", "evening", "started")
        self.assertTrue(sweep.valid_receipt(
            started, "2026-08-31", "evening", "run-1"))
        terminal_with_pending = receipt(
            "2026-08-31", "evening", "ran").replace(
                "Completed: none", "Completed: pending")
        self.assertFalse(sweep.valid_receipt(
            terminal_with_pending, "2026-08-31", "evening", "run-1"))

    @patch("sweep.get")
    def test_cleared_uses_default_branch_for_todo_baseline(self, get):
        def response(_, path):
            return {
                "": {"default_branch": "stable/v1"},
                "commits?sha=stable%2Fv1&path=TODO.md": [
                    {"sha": "inherited"}],
                "commits?sha=head-sha&path=TODO.md": [
                    {"sha": "inherited"}, {"sha": "branch-only"}],
            }[path]

        get.side_effect = response

        self.assertTrue(sweep.cleared("o/r", "head-sha", {}))
        self.assertIn(
            unittest.mock.call("o/r", "commits?sha=stable%2Fv1&path=TODO.md"),
            get.call_args_list)

    @patch("sweep.get")
    def test_review_comments_propagates_forbidden(self, get):
        get.side_effect = urllib.error.HTTPError(
            "https://api.github.test", 403, "Forbidden", {}, None)

        with self.assertRaises(urllib.error.HTTPError):
            sweep.review_comments("o/r", 7)

    @patch("sweep.get")
    def test_review_comments_suppresses_not_found(self, get):
        get.side_effect = urllib.error.HTTPError(
            "https://api.github.test", 404, "Not Found", {}, None)

        self.assertEqual(sweep.review_comments("o/r", 7), [])

    @patch("sweep.urllib.request.urlopen")
    def test_session_access_gate_is_distinct_from_clean(self, urlopen):
        body = io.BytesIO(b'{"message":"GitHub access is not enabled for this session"}')
        urlopen.side_effect = urllib.error.HTTPError(
            "https://api.github.test", 403, "Forbidden", {}, body)

        with self.assertRaises(sweep.NoAccess):
            sweep.get("o/r", "issues")

    @patch("sweep.config", return_value={})
    @patch("sweep.sweep", side_effect=sweep.NoAccess("blocked"))
    def test_main_returns_two_when_access_is_unavailable(self, _, __):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            status = sweep.main(["o/r"])

        self.assertEqual(status, 2)
        self.assertIn("not clean", output.getvalue())

    @patch("sweep.config", return_value={})
    @patch("sweep.sweep")
    def test_main_returns_two_for_unhandled_github_error(self, run, _):
        run.side_effect = urllib.error.HTTPError(
            "https://api.github.test", 404, "Not Found", {}, None)
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            status = sweep.main(["o/private"])

        self.assertEqual(status, 2)
        self.assertIn("GitHub HTTP 404 Not Found; not clean", output.getvalue())


if __name__ == "__main__":
    unittest.main()
