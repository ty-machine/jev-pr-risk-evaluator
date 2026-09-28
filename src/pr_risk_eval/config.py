from __future__ import annotations

import json
from copy import deepcopy
from importlib.resources import files
from pathlib import Path
from typing import Any


def load_config(path: str | None = None) -> dict[str, Any]:
    if path:
        with Path(path).open(encoding="utf-8") as handle:
            config = json.load(handle)
    else:
        resource = files("pr_risk_eval").joinpath("default_rubric.json")
        config = json.loads(resource.read_text(encoding="utf-8"))
    validate_config(config)
    return deepcopy(config)


def validate_config(config: dict[str, Any]) -> None:
    required = {"model", "endpoint", "chunk_max_chars", "thresholds", "questions"}
    missing = required - set(config)
    if missing:
        raise ValueError(f"rubric is missing keys: {', '.join(sorted(missing))}")
    if not isinstance(config["questions"], list) or not config["questions"]:
        raise ValueError("rubric.questions must be a non-empty array")
    ids: set[str] = set()
    for question in config["questions"]:
        for key in ("id", "label", "instructions", "criteria", "applies_to", "category"):
            if key not in question:
                raise ValueError(f"rubric question is missing {key}")
        if question["id"] in ids:
            raise ValueError(f"duplicate question id: {question['id']}")
        ids.add(question["id"])
        if set(question["criteria"]) != {"true", "false"}:
            raise ValueError(f"{question['id']} criteria must define true and false")
    for list_name in ("block_questions", "security_questions"):
        unknown = set(config["thresholds"].get(list_name, [])) - ids
        if unknown:
            raise ValueError(f"thresholds.{list_name} references unknown questions: {', '.join(sorted(unknown))}")
    for key in ("review_probability", "risk_reporting_probability", "block_probability", "minimum_confidence"):
        value = config["thresholds"].get(key)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"thresholds.{key} must be between 0 and 1")
