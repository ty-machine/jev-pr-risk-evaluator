# Contributing

Thanks for helping improve Jev PR Risk Evaluator.

## Development

The project requires Python 3.11+ and has no runtime dependencies.

```sh
PYTHONPATH=src python3 -m unittest discover -v
./pr-risk evaluate --diff examples/risky-auth.diff --replay examples/risky-auth.responses.json
```

Keep deterministic checks in normal Python code. Use Jev only for bounded semantic judgments, keep questions narrow, and make final routing decisions in the policy layer.

When changing the rubric or routing policy:

- add or update offline fixtures;
- test auto-approval, targeted-review, and blocking paths;
- preserve structured JSON compatibility when practical;
- document any new threshold or reviewer category.

Do not include real credentials, customer data, proprietary diffs, or live API responses containing sensitive source material.

## Pull requests

Explain the behavior change, include tests, and note whether the default rubric or thresholds changed. By participating, you agree that your contributions are licensed under the MIT License.
