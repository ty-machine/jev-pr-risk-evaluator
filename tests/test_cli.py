from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliTest(unittest.TestCase):
    def test_offline_replay_json(self) -> None:
        process = subprocess.run(
            [
                sys.executable, str(ROOT / "pr-risk"), "evaluate",
                "--diff", str(ROOT / "examples" / "risky-auth.diff"),
                "--replay", str(ROOT / "examples" / "risky-auth.responses.json"),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["route"], "review_required")
        self.assertEqual(result["chunks_evaluated"], 1)
    def test_staged_outside_git_repo_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run(
                [
                    sys.executable, str(ROOT / "pr-risk"), "evaluate",
                    "--staged", "--repo", directory,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(process.returncode, 2)
        self.assertIn("is not a Git repository", process.stderr)
        self.assertIn("--repo PATH", process.stderr)



if __name__ == "__main__":
    unittest.main()
