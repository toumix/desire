import contextlib
import io
import unittest
import urllib.error
from unittest.mock import patch

import sweep


class SweepEvidenceTest(unittest.TestCase):
    def test_config_records_expected_routine_days(self):
        self.assertEqual(
            sweep.config(sweep.CONFIG)["ROUTINE_DAYS"],
            "Mon,Tue,Wed,Thu,Fri")

    @patch("sweep.get")
    def test_work_state_lists_live_main_and_all_owned_heads(self, get):
        get.side_effect = lambda _, path: {
            "commits/main": {"sha": "abc123"},
            "pulls?state=open": [
                {"number": 3, "user": {"login": "agent"}},
                {"number": 7, "user": {"login": "other"}},
                {"number": 9, "user": {"login": "other"}},
            ],
        }[path]
        setup = {"AGENT": "agent", "ADOPTED_PRS": {"o/r": [7]}}

        self.assertEqual(
            sweep.work_state("o/r", setup, {}),
            "o/r: live main abc123; open AGENT-owned PRs #3,#7")

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

        get.return_value = [
            pull(4, "open", "2026-08-31T08:00:00Z", "2026-08-31"),
            pull(3, "closed", "2026-08-31T07:00:00Z", "2026-08-30", merged=True),
            pull(2, "closed", "2026-08-29T07:00:00Z", "2026-08-29"),
        ]
        output = io.StringIO()

        with contextlib.redirect_stderr(output):
            findings = sweep.memory("o/memory", "2026-08-30T03:00:00Z")

        self.assertEqual(findings, [])
        self.assertIn("#4 open 2026-08-31T08:00:00Z head-4@sha-4", output.getvalue())
        self.assertIn("#3 merged 2026-08-31T07:00:00Z head-3@sha-3", output.getvalue())
        self.assertNotIn("#2 closed", output.getvalue())

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


if __name__ == "__main__":
    unittest.main()
