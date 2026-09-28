from __future__ import annotations

from typing import Any

from .diff_parser import chunk_diff, parse_diff
from .jev import JevClient
from .models import ChunkJudgment, EvaluationResult


IMPACT_SCORE = {"low": 0.1, "moderate": 0.4, "high": 0.75, "critical": 1.0}
ROUTE_LABEL = {
    "normal_review": "Normal review",
    "specialist_security_review": "Specialist/security review",
    "block_require_approval": "Block / require approval",
}


def evaluate_diff(
    diff_text: str,
    client: JevClient,
    config: dict[str, Any],
    *,
    title: str | None = None,
    description: str | None = None,
) -> EvaluationResult:
    facts = parse_diff(diff_text)
    if not facts.files:
        raise ValueError("input does not contain a unified git diff (expected 'diff --git' headers)")
    chunks = chunk_diff(facts, int(config["chunk_max_chars"]))
    judgments = [
        client.evaluate(
            chunk=chunk,
            facts=facts,
            questions=config["questions"],
            config=config,
            title=title,
            description=description,
        )
        for chunk in chunks
    ]
    return aggregate(facts, judgments, config)



def aggregate(facts: Any, judgments: list[ChunkJudgment], config: dict[str, Any]) -> EvaluationResult:
    probabilities: dict[str, float | None] = {question["id"]: None for question in config["questions"]}
    evidence: dict[str, dict[str, Any]] = {}
    file_tags = {item.path: set(item.tags) for item in facts.files}
    for judgment in judgments:
        for question_id, probability in judgment.questions.items():
            if probabilities[question_id] is None or probability >= probabilities[question_id]:
                probabilities[question_id] = probability
                evidence[question_id] = {
                    "path": judgment.path,
                    "chunk": judgment.chunk_index,
                    "probability": probability,
                    "tags": sorted(file_tags.get(judgment.path, set())),
                }

    thresholds = config["thresholds"]
    review_threshold = float(thresholds["review_probability"])
    report_threshold = float(thresholds.get("risk_reporting_probability", 0.35))
    block_threshold = float(thresholds["block_probability"])
    min_confidence = float(thresholds["minimum_confidence"])
    question_by_id = {question["id"]: question for question in config["questions"]}
    reviewer_data: dict[str, dict[str, Any]] = {}

    def add_reviewer(team: str, reason: str, confidence: float, signal: str, item_evidence: dict[str, Any] | None) -> None:
        reviewer = reviewer_data.setdefault(
            team,
            {"team": team, "required": True, "confidence": 0.0, "reasons": [], "evidence": []},
        )
        reviewer["confidence"] = max(reviewer["confidence"], confidence)
        if reason not in reviewer["reasons"]:
            reviewer["reasons"].append(reason)
        if item_evidence:
            entry = {"signal": signal, **item_evidence}
            if entry not in reviewer["evidence"]:
                reviewer["evidence"].append(entry)

    def owners_for(tags: set[str], question_id: str) -> list[str]:
        owners: list[str] = []
        if "infra" in tags or question_id in {"infra_destructive_change", "dependency_upgrade_risk"}:
            owners.append("Infra/Platform/SRE")
        if "app" in tags:
            owners.append("App")
        return owners

    risk_types: list[dict[str, Any]] = []
    for question_id, probability in probabilities.items():
        if probability is None or probability < report_threshold:
            continue
        question = question_by_id[question_id]
        risk_types.append(
            {
                "type": question["category"],
                "signal": question_id,
                "label": question["label"],
                "probability": round(probability, 4),
                "evidence": evidence.get(question_id),
            }
        )
    risk_types.sort(key=lambda item: item["probability"], reverse=True)

    security_questions = set(thresholds["security_questions"])
    infra_questions = {
        "infra_destructive_change", "route_or_feature_removal", "dependency_upgrade_risk",
        "operational_risk", "rollback_difficulty", "human_approval_needed",
    }
    app_questions = {
        "app_extensive_change", "route_or_feature_removal", "data_loss_corruption",
        "operational_risk", "rollback_difficulty", "human_approval_needed",
    }
    for question_id, probability in probabilities.items():
        if probability is None or probability < review_threshold:
            continue
        item_evidence = evidence.get(question_id)
        tags = set(item_evidence.get("tags", [])) if item_evidence else set()
        reason = f"{question_by_id[question_id]['label']} (p={probability:.2f})"
        if question_id in security_questions:
            add_reviewer("Security", reason, probability, question_id, item_evidence)
        if question_id in infra_questions and ("infra" in tags or question_id == "dependency_upgrade_risk"):
            add_reviewer("Infra/Platform/SRE", reason, probability, question_id, item_evidence)
        if question_id in app_questions and "app" in tags:
            add_reviewer("App", reason, probability, question_id, item_evidence)

    for judgment in judgments:
        tags = file_tags.get(judgment.path, set())
        high_impact = (
            judgment.impact_probabilities.get("high", 0.0)
            + judgment.impact_probabilities.get("critical", 0.0)
        )
        for team in owners_for(tags, ""):
            if high_impact >= review_threshold:
                add_reviewer(
                    team,
                    f"High-or-critical impact is plausible for {judgment.path} (p={high_impact:.2f})",
                    high_impact,
                    "impact_level",
                    {"path": judgment.path, "chunk": judgment.chunk_index},
                )

    critical_findings = [item for item in facts.deterministic_findings if item["severity"] == "critical"]
    for finding in critical_findings:
        add_reviewer(
            "Security",
            finding["message"],
            1.0,
            finding["id"],
            {"path": finding["path"]},
        )
        risk_types.append(
            {
                "type": "security",
                "signal": finding["id"],
                "label": finding["message"],
                "probability": 1.0,
                "evidence": {"path": finding["path"]},
            }
        )

    blocking = [
        question_id
        for question_id in thresholds["block_questions"]
        if (probabilities.get(question_id) or 0.0) >= block_threshold
    ]
    critical_impact = max(
        (item.impact_probabilities.get("critical", 0.0) for item in judgments),
        default=0.0,
    )
    is_blocked = bool(critical_findings or blocking or critical_impact >= block_threshold)
    reviewers = sorted(
        reviewer_data.values(),
        key=lambda item: ({"Security": 0, "Infra/Platform/SRE": 1, "App": 2}.get(item["team"], 9), -item["confidence"]),
    )
    for reviewer in reviewers:
        reviewer["confidence"] = round(reviewer["confidence"], 4)

    auto_approve = not is_blocked and not reviewers
    route = "block_require_approval" if is_blocked else ("review_required" if reviewers else "auto_approve")
    impact_risk = max(
        (IMPACT_SCORE[item.impact_level] * max(item.impact_confidence, 0.5) for item in judgments),
        default=0.0,
    )
    semantic_risk = max((value for value in probabilities.values() if value is not None), default=0.0)
    deterministic_risk = 1.0 if critical_findings else (0.75 if facts.deterministic_findings else 0.0)
    risk_score = max(semantic_risk, impact_risk, deterministic_risk)
    confidence = min((item.impact_confidence for item in judgments), default=0.0)

    if is_blocked:
        reasons = [
            f"{question_by_id[qid]['label']} (p={probabilities[qid] or 0.0:.2f})"
            for qid in blocking
        ]
        reasons.extend(item["message"] for item in critical_findings)
        if critical_impact >= block_threshold:
            reasons.append(f"Critical impact is plausible (p={critical_impact:.2f}).")
    elif reviewers:
        reasons = [f"{item['team']}: {item['reasons'][0]}" for item in reviewers]
    else:
        reasons = [
            "No team-specific review threshold was crossed; automated checks may approve this change."
        ]

    costs = [item.cost_usd for item in judgments if item.cost_usd is not None]
    models = sorted({item.model for item in judgments})
    warnings = [
        "This is risk triage, not proof that a change is safe. Required automated checks must still pass."
    ]
    uncertain_chunks = sum(item.impact_confidence < min_confidence for item in judgments)
    if uncertain_chunks:
        warnings.append(
            f"{uncertain_chunks} chunk assessment(s) had low impact confidence; this is reported but does not alone require human review.")
    if facts.binary_files:
        warnings.append(f"{facts.binary_files} binary file(s) could not be semantically inspected from the diff.")
    labels = {
        "auto_approve": "Auto-approve recommended",
        "review_required": "Targeted review required",
        "block_require_approval": "Block / explicit approval required",
    }
    summary = f"{labels[route]}: risk {risk_score:.2f}, assessment confidence {confidence:.2f}."
    return EvaluationResult(
        schema_version="2.0",
        route=route,
        auto_approve=auto_approve,
        risk_score=round(risk_score, 4),
        confidence=round(confidence, 4),
        risk_types=risk_types,
        reviewers=reviewers,
        summary=summary,
        reasons=reasons,
        facts=facts.summary(),
        question_probabilities={
            key: round(value, 4) if value is not None else None
            for key, value in probabilities.items()
        },
        evidence=evidence,
        deterministic_findings=facts.deterministic_findings,
        chunks_evaluated=len(judgments),
        model=", ".join(models),
        total_cost_usd=round(sum(costs), 9) if costs else None,
        warnings=warnings,
    )
