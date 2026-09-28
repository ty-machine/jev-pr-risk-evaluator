from __future__ import annotations

import unittest

from pr_risk_eval.diff_parser import chunk_diff, parse_diff


DIFF = """diff --git a/app/auth.py b/app/auth.py
index 1111111..2222222 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -1,2 +1,3 @@
-check(user)
+token = request.token
+allow(user)
 context()
diff --git a/tests/test_auth.py b/tests/test_auth.py
new file mode 100644
--- /dev/null
+++ b/tests/test_auth.py
@@ -0,0 +1 @@
+def test_auth(): pass
"""


class DiffParserTest(unittest.TestCase):
    def test_extracts_deterministic_facts_and_tags(self) -> None:
        facts = parse_diff(DIFF)
        self.assertEqual(len(facts.files), 2)
        self.assertEqual((facts.additions, facts.deletions), (3, 1))
        self.assertEqual(facts.test_files, 1)
        self.assertIn("auth", facts.tags)
        self.assertEqual(facts.files[1].status, "added")

    def test_chunks_long_hunks_without_losing_file_context(self) -> None:
        facts = parse_diff(DIFF)
        chunks = chunk_diff(facts, 35)
        self.assertGreater(len(chunks), 2)
        self.assertEqual(chunks[0].path, "app/auth.py")
        self.assertIn("auth", chunks[0].file_facts["tags"])

    def test_flags_possible_secret_without_copying_value_to_finding(self) -> None:
        diff = """diff --git a/config.py b/config.py
--- a/config.py
+++ b/config.py
@@ -0,0 +1 @@
+api_key = \"abcdefghijklmnopqrstuv\"
"""
        findings = parse_diff(diff).deterministic_findings
        self.assertEqual(findings[0]["id"], "possible_secret")
        self.assertNotIn("abcdefghijkl", str(findings[0]))


if __name__ == "__main__":
    unittest.main()
