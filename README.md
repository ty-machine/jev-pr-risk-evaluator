# Jev PR Risk Evaluator

[![tests](https://github.com/ty-machine/jev-pr-risk-evaluator/actions/workflows/test.yml/badge.svg)](https://github.com/ty-machine/jev-pr-risk-evaluator/actions/workflows/test.yml) [![MIT license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A small, CLI-first pull-request risk triage tool. It extracts exact facts from a local git diff, sends only focused file/hunk context to TypeSafe Jev through OpenRouter, aggregates the typed probabilities in code, and returns one of three routes:

- `auto_approve`
- `review_required` with targeted App, Infra/Platform/SRE, and/or Security reviewers
- `block_require_approval`

It is a prioritization aid, not a claim that a pull request is safe.
Status: experimental MVP. Calibrate the rubric against your own labeled pull requests before enforcing automatic merge decisions.


## Requirements

- Python 3.11+
- An OpenRouter API key for live evaluation

There are no runtime Python dependencies.

## Quick start

Run directly from the checkout:

```sh
./pr-risk evaluate --diff change.diff
./pr-risk evaluate --staged
./pr-risk evaluate --base origin/main --json
./pr-risk evaluate --repo /path/to/another/repository --staged
git diff origin/main...HEAD | ./pr-risk evaluate --diff -
```

Or install an editable command:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
pr-risk evaluate --staged
```

For a live call, provide the key only through the process environment:

```sh
export OPENROUTER_API_KEY="..."
./pr-risk evaluate --staged
```

Do not put a real key in this repository or pass it as a command-line argument. With 1Password CLI, prefer an `op run` environment template containing an `op://vault/item/field` reference; `op run` injects the value into the child process without writing the secret to the template or command line.

## Offline demo

The replay fixture exercises the same response validation and policy without a network call:

```sh
./pr-risk evaluate \
  --diff examples/risky-auth.diff \
  --replay examples/risky-auth.responses.json
```

Add `--json` for stable structured output suitable for CI. A live failure exits with status 2 rather than treating an unavailable model as a clean PR.

## How it works

1. **Deterministic facts:** local code parses file status, additions/deletions, binaries, test coverage signals, sensitive path classes, migrations, and possible added credential patterns.
2. **Focused Jev judgments:** each file is split on logical diff hunks with a configurable size cap. Only questions applicable to that file's tags are included. Jev receives the patch, compact file facts, and a PR-level count summary—not the entire repository.
3. **Code aggregation:** the maximum probability for each named risk across chunks is retained with its source path/chunk. No model performs arithmetic, assigns reviewers, or chooses the final route.
4. **Ownership policy:** low-risk additive changes can be auto-approved. Infrastructure risks route to Infra/Platform/SRE, extensive functionality changes to App, and risky credentials or sensitive-data handling to Security. High-probability destructive or irreversible changes block.

The rubric covers the original safety checks plus destructive infrastructure changes, route or feature removals, extensive existing-feature changes, and risky dependency or platform upgrades.

## Configuration

The bundled JSON rubric is [`src/pr_risk_eval/default_rubric.json`](src/pr_risk_eval/default_rubric.json). Copy it and pass `--config your-rubric.json` to tune:

- model and Decisions API endpoint
- maximum chunk size
- review, risk-reporting, blocking, and minimum-confidence thresholds
- which questions can block or trigger targeted team review
- question wording, criteria, categories, and file-tag applicability

Thresholds are starting points. Calibrate them against a labeled set of your own accepted, escalated, and blocked pull requests before using the result as a required gate.

## Tests

All normal tests are offline:

```sh
PYTHONPATH=src python3 -m unittest discover -v
```

The optional integration test is explicit and billable:

```sh
PR_RISK_LIVE_TEST=1 OPENROUTER_API_KEY="..." \
  PYTHONPATH=src python3 -m unittest tests.test_live -v
```

## API choice

The implementation follows OpenRouter's current Jev interface: `POST https://openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.13`, with a body containing `model`, `state`, and typed `questions`. It validates `noul` probabilities and the `choice` distribution/confidence before policy code uses them. See OpenRouter's [Jev tutorial](https://openrouter.ai/blog/tutorials/how-to-use-jev/) and [Jev model page](https://openrouter.ai/typesafe/jev-1.13/api).

## Known MVP limits

- Input is a local unified git diff; GitHub/GitLab fetching and PR comments are intentionally out of scope.
- Renames, binary files, and generated code receive limited semantic inspection.
- The path classifier is heuristic and should be adapted to repository conventions.
- Evaluation is sequential to keep behavior and cost obvious; a production service can add bounded concurrency and retries.
