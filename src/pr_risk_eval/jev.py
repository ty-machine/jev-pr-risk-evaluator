from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from .models import ChunkJudgment, DiffChunk, DiffFacts


class JevError(RuntimeError):
    """A safe-to-display Jev transport or response error."""


class JevClient(Protocol):
    def evaluate(
        self,
        *,
        chunk: DiffChunk,
        facts: DiffFacts,
        questions: list[dict[str, Any]],
        config: dict[str, Any],
        title: str | None,
        description: str | None,
    ) -> ChunkJudgment: ...


def applicable_questions(chunk: DiffChunk, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tags = set(chunk.file_facts.get("tags", []))
    return [
        question for question in questions
        if "always" in question["applies_to"] or tags.intersection(question["applies_to"])
    ]


def build_request(
    chunk: DiffChunk,
    facts: DiffFacts,
    questions: list[dict[str, Any]],
    config: dict[str, Any],
    title: str | None,
    description: str | None,
) -> dict[str, Any]:
    selected = applicable_questions(chunk, questions)
    typed_questions: dict[str, Any] = {
        question["id"]: {
            "type": "noul",
            "instructions": question["instructions"],
            "criteria": question["criteria"],
        }
        for question in selected
    }
    typed_questions["impact_level"] = {
        "type": "choice",
        "instructions": "What is the highest plausible impact level of the change shown in `change.patch`, considering `change.file_facts` and `pr_facts`?",
        "criteria": config["impact_levels"],
    }
    state: dict[str, Any] = {
        "pr_facts": facts.summary(),
        "change": {
            "path": chunk.path,
            "chunk": f"{chunk.index}/{chunk.total_for_file}",
            "file_facts": chunk.file_facts,
            "patch": chunk.patch,
        },
    }
    if title:
        state["pr_title"] = title
    if description:
        state["pr_description"] = description
    return {"model": config["model"], "state": state, "questions": typed_questions}


def _probability(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1:
        raise JevError(f"invalid probability for {label}")
    return float(value)


def parse_response(payload: dict[str, Any], selected_ids: set[str], chunk: DiffChunk) -> ChunkJudgment:
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise JevError("Decisions response did not contain an answers object")
    values: dict[str, float] = {}
    for question_id in selected_ids:
        answer = answers.get(question_id)
        if not isinstance(answer, dict) or answer.get("type") != "noul":
            raise JevError(f"missing or invalid noul answer for {question_id}")
        values[question_id] = _probability(answer.get("noul"), question_id)
    impact = answers.get("impact_level")
    if not isinstance(impact, dict) or impact.get("type") != "choice":
        raise JevError("missing or invalid choice answer for impact_level")
    choice = impact.get("choice")
    if choice not in {"low", "moderate", "high", "critical"}:
        raise JevError("unknown impact_level choice")
    probabilities = impact.get("probabilities")
    if not isinstance(probabilities, dict):
        raise JevError("impact_level did not include probabilities")
    parsed_probabilities = {str(key): _probability(value, f"impact_level.{key}") for key, value in probabilities.items()}
    if set(parsed_probabilities) != {"low", "moderate", "high", "critical"}:
        raise JevError("impact_level probabilities did not contain the configured options")
    if not 0.99 <= sum(parsed_probabilities.values()) <= 1.01:
        raise JevError("impact_level probabilities did not sum to 1")
    confidence = _probability(impact.get("confidence"), "impact_level.confidence")
    usage = payload.get("usage", {})
    cost = usage.get("cost") if isinstance(usage, dict) else None
    if cost is not None and (not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0):
        raise JevError("invalid usage cost")
    model = payload.get("model")
    if not isinstance(model, str) or not model:
        raise JevError("Decisions response did not contain a model")
    return ChunkJudgment(
        path=chunk.path,
        chunk_index=chunk.index,
        questions=values,
        impact_level=choice,
        impact_confidence=confidence,
        impact_probabilities=parsed_probabilities,
        model=model,
        request_id=payload.get("id") if isinstance(payload.get("id"), str) else None,
        cost_usd=float(cost) if cost is not None else None,
    )


class OpenRouterJevClient:
    def __init__(self, api_key: str, *, timeout: float = 60.0):
        if not api_key:
            raise JevError("OPENROUTER_API_KEY is not set")
        self._api_key = api_key
        self._timeout = timeout

    def evaluate(
        self, *, chunk: DiffChunk, facts: DiffFacts, questions: list[dict[str, Any]],
        config: dict[str, Any], title: str | None, description: str | None,
    ) -> ChunkJudgment:
        selected = applicable_questions(chunk, questions)
        body = json.dumps(build_request(chunk, facts, questions, config, title, description)).encode("utf-8")
        request = urllib.request.Request(
            config["endpoint"],
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": "jev-pr-risk/0.1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise JevError(f"OpenRouter Decisions API returned HTTP {error.code}") from None
        except urllib.error.URLError as error:
            raise JevError(f"OpenRouter Decisions API was unavailable: {error.reason}") from None
        except TimeoutError:
            raise JevError("OpenRouter Decisions API timed out") from None
        except json.JSONDecodeError:
            raise JevError("OpenRouter Decisions API returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise JevError("OpenRouter Decisions API returned an invalid response")
        return parse_response(payload, {item["id"] for item in selected}, chunk)


class ReplayJevClient:
    """Offline response replay for tests, demos, and policy tuning."""

    def __init__(self, path: str):
        with Path(path).open(encoding="utf-8") as handle:
            payload = json.load(handle)
        responses = payload.get("responses") if isinstance(payload, dict) else None
        if not isinstance(responses, list) or not responses:
            raise JevError("replay file must contain a non-empty responses array")
        self._responses = responses
        self._index = 0

    def evaluate(
        self, *, chunk: DiffChunk, facts: DiffFacts, questions: list[dict[str, Any]],
        config: dict[str, Any], title: str | None, description: str | None,
    ) -> ChunkJudgment:
        if self._index >= len(self._responses):
            raise JevError("replay file has fewer responses than diff chunks")
        payload = self._responses[self._index]
        self._index += 1
        selected = applicable_questions(chunk, questions)
        return parse_response(payload, {item["id"] for item in selected}, chunk)
