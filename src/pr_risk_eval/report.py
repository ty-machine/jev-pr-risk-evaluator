from __future__ import annotations

from .models import EvaluationResult



def terminal_report(result: EvaluationResult) -> str:
    labels = {
        "auto_approve": "AUTO-APPROVE RECOMMENDED",
        "review_required": "TARGETED REVIEW REQUIRED",
        "block_require_approval": "BLOCK / EXPLICIT APPROVAL REQUIRED",
    }
    lines = [
        f"PR decision: {labels[result.route]}",
        f"Risk score: {result.risk_score:.2f}    Assessment confidence: {result.confidence:.2f}",
        f"Scope: {result.facts['files_changed']} files, +{result.facts['additions']} -{result.facts['deletions']}, {result.chunks_evaluated} semantic chunk(s)",
    ]
    if result.reviewers:
        lines.extend(["", "Reviewers:"])
        for reviewer in result.reviewers:
            lines.append(f"  - {reviewer['team']} (confidence {reviewer['confidence']:.2f})")
            lines.extend(f"      {reason}" for reason in reviewer["reasons"])
    else:
        lines.extend(["", "Reviewers: none"])

    if result.risk_types:
        lines.extend(["", "Risk types:"])
        lines.extend(
            f"  - {item['type']}: {item['label']} (p={item['probability']:.2f})"
            for item in result.risk_types
        )
    else:
        lines.extend(["", "Risk types: none above the reporting threshold"])

    lines.extend(["", "Decision reasons:"])
    lines.extend(f"  - {reason}" for reason in result.reasons)
    if result.deterministic_findings:
        lines.extend(["", "Deterministic findings:"])
        lines.extend(
            f"  - [{item['severity']}] {item['path']}: {item['message']}"
            for item in result.deterministic_findings
        )
    lines.extend(["", f"Model: {result.model}"])
    if result.total_cost_usd is not None:
        lines.append(f"OpenRouter cost: ${result.total_cost_usd:.9f}")
    lines.extend(["", *(f"Note: {warning}" for warning in result.warnings)])
    return "\n".join(lines)
