from __future__ import annotations

import unittest

from pr_risk_eval.config import load_config
from pr_risk_eval.diff_parser import chunk_diff, parse_diff
from pr_risk_eval.jev import JevError, applicable_questions, build_request, parse_response

from .test_diff_parser import DIFF


class JevProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.facts = parse_diff(DIFF)
        self.chunk = chunk_diff(self.facts, 12000)[0]

    def test_builds_current_openrouter_decisions_shape(self) -> None:
        request = build_request(self.chunk, self.facts, self.config["questions"], self.config, "T", None)
        self.assertEqual(request["model"], "typesafe/jev-1.13")
        self.assertIn("state", request)
        self.assertEqual(request["questions"]["authz_boundary"]["type"], "noul")
        self.assertEqual(request["questions"]["impact_level"]["type"], "choice")
        self.assertNotIn("irreversible_migration", request["questions"])

    def test_parse_rejects_missing_answers(self) -> None:
        selected = {item["id"] for item in applicable_questions(self.chunk, self.config["questions"])}
        with self.assertRaises(JevError):
            parse_response({"model": "x", "answers": {}}, selected, self.chunk)


if __name__ == "__main__":
    unittest.main()
