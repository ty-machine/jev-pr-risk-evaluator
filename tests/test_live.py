from __future__ import annotations

import os
import unittest

from pr_risk_eval.config import load_config
from pr_risk_eval.evaluator import evaluate_diff
from pr_risk_eval.jev import OpenRouterJevClient


@unittest.skipUnless(
    os.environ.get("PR_RISK_LIVE_TEST") == "1" and os.environ.get("OPENROUTER_API_KEY"),
    "set PR_RISK_LIVE_TEST=1 and OPENROUTER_API_KEY to run the billable integration test",
)
class LiveIntegrationTest(unittest.TestCase):
    def test_openrouter_decisions_api(self) -> None:
        diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-Old title
+Clearer title
"""
        result = evaluate_diff(diff, OpenRouterJevClient(os.environ["OPENROUTER_API_KEY"]), load_config())
        self.assertGreater(result.confidence, 0)
        self.assertGreater(result.chunks_evaluated, 0)


if __name__ == "__main__":
    unittest.main()
