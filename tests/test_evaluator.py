from __future__ import annotations

import unittest

from pr_risk_eval.config import load_config
from pr_risk_eval.evaluator import aggregate
from pr_risk_eval.diff_parser import parse_diff
from pr_risk_eval.models import ChunkJudgment

from .test_diff_parser import DIFF


def judgment(**probabilities: float) -> ChunkJudgment:
    return ChunkJudgment(
        path="app/auth.py",
        chunk_index=1,
        questions=probabilities,
        impact_level="high",
        impact_confidence=0.9,
        impact_probabilities={"low": 0.01, "moderate": 0.04, "high": 0.9, "critical": 0.05},
        model="typesafe/jev-1.13-test",
        cost_usd=0.00001,
    )


def low_judgment(**probabilities: float) -> ChunkJudgment:
    item = judgment(**probabilities)
    item.impact_level = "low"
    item.impact_confidence = 0.9
    item.impact_probabilities = {"low": 0.9, "moderate": 0.06, "high": 0.03, "critical": 0.01}
    return item


class PolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.facts = parse_diff(DIFF)

    def test_security_signal_routes_to_specialist(self) -> None:
        result = aggregate(self.facts, [judgment(authz_boundary=0.8, security_review_needed=0.9)], self.config)
        self.assertEqual(result.route, "review_required")
        self.assertEqual(result.reviewers[0]["team"], "Security")
        self.assertFalse(result.auto_approve)

    def test_high_destructive_signal_blocks(self) -> None:
        result = aggregate(self.facts, [judgment(data_loss_corruption=0.91)], self.config)
        self.assertEqual(result.route, "block_require_approval")

    def test_high_impact_routes_to_owner_review(self) -> None:
        item = judgment(testing_insufficient=0.1)
        item.impact_confidence = 0.2
        result = aggregate(self.facts, [item], self.config)
        self.assertEqual(result.route, "review_required")

    def test_low_signals_allow_normal_review(self) -> None:
        result = aggregate(self.facts, [low_judgment(testing_insufficient=0.1, operational_risk=0.2)], self.config)
        self.assertEqual(result.route, "auto_approve")
        self.assertTrue(result.auto_approve)
        self.assertIsNone(result.question_probabilities["irreversible_migration"])
    def test_destructive_terraform_routes_only_to_infra(self) -> None:
        infra_diff = """diff --git a/infra/main.tf b/infra/main.tf
--- a/infra/main.tf
+++ b/infra/main.tf
@@ -1 +1 @@
-resource "aws_route" "legacy" {}
+resource "aws_route" "replacement" {}
"""
        facts = parse_diff(infra_diff)
        item = low_judgment(infra_destructive_change=0.82, route_or_feature_removal=0.72)
        item.path = "infra/main.tf"
        result = aggregate(facts, [item], self.config)
        self.assertEqual(result.route, "review_required")
        self.assertEqual([reviewer["team"] for reviewer in result.reviewers], ["Infra/Platform/SRE"])

    def test_small_additive_terraform_can_auto_approve(self) -> None:
        infra_diff = """diff --git a/infra/labels.tf b/infra/labels.tf
--- a/infra/labels.tf
+++ b/infra/labels.tf
@@ -1 +1,2 @@
 locals {}
+output "environment" { value = "test" }
"""
        facts = parse_diff(infra_diff)
        item = low_judgment(
            infra_destructive_change=0.05,
            route_or_feature_removal=0.03,
            dependency_upgrade_risk=0.08,
            operational_risk=0.12,
            testing_insufficient=0.83,
        )
        item.path = "infra/labels.tf"
        item.impact_confidence = 0.24
        result = aggregate(facts, [item], self.config)
        self.assertTrue(result.auto_approve)
        self.assertEqual(result.reviewers, [])



if __name__ == "__main__":
    unittest.main()
