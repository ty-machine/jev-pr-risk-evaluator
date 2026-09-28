from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FileChange:
    old_path: str
    path: str
    status: str = "modified"
    additions: int = 0
    deletions: int = 0
    binary: bool = False
    hunks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class DiffFacts:
    files: list[FileChange]
    additions: int
    deletions: int
    binary_files: int
    test_files: int
    code_files: int
    tags: list[str]
    deterministic_findings: list[dict[str, Any]]

    def summary(self) -> dict[str, Any]:
        return {
            "files_changed": len(self.files),
            "additions": self.additions,
            "deletions": self.deletions,
            "binary_files": self.binary_files,
            "test_files": self.test_files,
            "code_files": self.code_files,
            "tags": self.tags,
        }


@dataclass
class DiffChunk:
    path: str
    index: int
    total_for_file: int
    patch: str
    file_facts: dict[str, Any]


@dataclass
class SemanticAnswer:
    probability: float
    chunk_path: str
    chunk_index: int


@dataclass
class ChunkJudgment:
    path: str
    chunk_index: int
    questions: dict[str, float]
    impact_level: str
    impact_confidence: float
    impact_probabilities: dict[str, float]
    model: str
    request_id: str | None = None
    cost_usd: float | None = None


@dataclass
class EvaluationResult:
    schema_version: str
    route: str
    auto_approve: bool
    risk_score: float
    confidence: float
    risk_types: list[dict[str, Any]]
    reviewers: list[dict[str, Any]]
    summary: str
    reasons: list[str]
    facts: dict[str, Any]
    question_probabilities: dict[str, float | None]
    evidence: dict[str, dict[str, Any]]
    deterministic_findings: list[dict[str, Any]]
    chunks_evaluated: int
    model: str
    total_cost_usd: float | None
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
