# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability or accidental credential exposure.

Use GitHub's private vulnerability reporting feature on this repository. Include the affected version, reproduction details, impact, and any suggested mitigation. Maintainers will acknowledge reports as soon as practical and coordinate disclosure after a fix is available.

## Scope and data handling

The evaluator sends selected diff chunks and compact metadata to OpenRouter when live evaluation is enabled. Do not evaluate source that your organization is not permitted to send to that service.

API keys must be provided through the environment or a secret manager. Never place keys in configuration files, fixtures, command arguments, issues, or pull requests.

The tool provides risk triage, not a security guarantee. Required tests, branch protections, and accountable human review remain part of the security boundary.
