from __future__ import annotations

import re
from pathlib import PurePosixPath

from .models import DiffChunk, DiffFacts, FileChange


CODE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".ex", ".exs", ".go", ".h", ".hpp", ".java",
    ".js", ".jsx", ".kt", ".kts", ".php", ".py", ".rb", ".rs", ".scala",
    ".sh", ".sql", ".swift", ".ts", ".tsx", ".vue",
}
TEST_MARKERS = ("/test/", "/tests/", "/spec/", "_test.", ".test.", ".spec.", "test_")
AUTH_MARKERS = ("auth", "oauth", "permission", "policy", "rbac", "acl", "session", "identity")
DATA_MARKERS = ("database", "schema", "model", "repository", "storage", "sql", "persistence")
MIGRATION_MARKERS = ("migration", "migrations", "alembic", "flyway", "liquibase", "schema.sql")
OPS_MARKERS = ("docker", "kubernetes", "k8s", "helm", "terraform", "deploy", "workflow", ".github/")
SENSITIVE_MARKERS = ("secret", "credential", "token", "password", "privacy", "pii", "payment", "billing")
INFRA_MARKERS = (".github/workflows/", "terraform", "terragrunt", "pulumi", "cloudformation", "kubernetes", "k8s", "helm", "ansible", "dockerfile", "deploy/", "infrastructure/", "infra/")
INFRA_SUFFIXES = {".tf", ".tfvars", ".hcl"}
DEPENDENCY_FILES = {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "requirements.txt", "poetry.lock", "pipfile.lock", "go.mod", "go.sum", "cargo.toml", "cargo.lock", "gemfile.lock", "pom.xml", "build.gradle"}

SECRET_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[oprsu]_[A-Za-z0-9_]{20,}\b")),
    ("generic_secret_assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|password|token)\b\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"
    )),
]


def _clean_path(raw: str) -> str:
    raw = raw.strip().split("\t", 1)[0]
    return raw[2:] if raw.startswith(("a/", "b/")) else raw


def _path_tags(path: str) -> list[str]:
    value = "/" + path.lower()
    name = PurePosixPath(path).name.lower()
    tags: set[str] = set()
    if any(marker in value for marker in TEST_MARKERS) or name.startswith("test_"):
        tags.add("test")
    if any(marker in value for marker in AUTH_MARKERS):
        tags.add("auth")
    if any(marker in value for marker in DATA_MARKERS):
        tags.add("data")
    if any(marker in value for marker in MIGRATION_MARKERS):
        tags.add("migration")
    if any(marker in value for marker in OPS_MARKERS):
        tags.add("operations")
    if any(marker in value for marker in SENSITIVE_MARKERS):
        tags.add("sensitive")
    if any(marker in value for marker in INFRA_MARKERS) or PurePosixPath(path).suffix.lower() in INFRA_SUFFIXES:
        tags.update(("infra", "operations"))
    if name in DEPENDENCY_FILES or "dependabot" in value or "renovate" in value:
        tags.add("dependency")
    if PurePosixPath(path).suffix.lower() in CODE_SUFFIXES:
        tags.add("code")
    if path.lower().endswith((".md", ".rst", ".txt")) or value.startswith("/docs/"):
        tags.add("docs")
    if "code" in tags and "infra" not in tags and "test" not in tags:
        tags.add("app")
    return sorted(tags)


def parse_diff(text: str) -> DiffFacts:
    files: list[FileChange] = []
    current: FileChange | None = None
    current_hunk: list[str] | None = None

    def finish_hunk() -> None:
        nonlocal current_hunk
        if current is not None and current_hunk:
            current.hunks.append("\n".join(current_hunk))
        current_hunk = None

    for line in text.splitlines():
        if line.startswith("diff --git "):
            finish_hunk()
            match = re.match(r"diff --git a/(.*?) b/(.*)$", line)
            old_path, path = (match.group(1), match.group(2)) if match else ("unknown", "unknown")
            current = FileChange(old_path=old_path, path=path)
            files.append(current)
            continue
        if current is None:
            continue
        if line.startswith("new file mode"):
            current.status = "added"
        elif line.startswith("deleted file mode"):
            current.status = "deleted"
        elif line.startswith("rename from "):
            current.status = "renamed"
            current.old_path = line[len("rename from "):]
        elif line.startswith("rename to "):
            current.path = line[len("rename to "):]
        elif line.startswith("Binary files ") or line == "GIT binary patch":
            current.binary = True
        elif line.startswith("+++ ") and line[4:] != "/dev/null":
            current.path = _clean_path(line[4:])
        elif line.startswith("@@"):
            finish_hunk()
            current_hunk = [line]
        elif current_hunk is not None:
            current_hunk.append(line)
            if line.startswith("+") and not line.startswith("+++"):
                current.additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                current.deletions += 1
    finish_hunk()

    findings: list[dict[str, object]] = []
    for changed in files:
        changed.tags = _path_tags(changed.path)
        added_text = "\n".join(
            line[1:] for hunk in changed.hunks for line in hunk.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        for kind, pattern in SECRET_PATTERNS:
            if pattern.search(added_text):
                findings.append({
                    "id": "possible_secret",
                    "severity": "critical",
                    "path": changed.path,
                    "kind": kind,
                    "message": "A possible credential or private key was added; inspect the file before merge.",
                })
        if changed.status == "deleted" and "migration" in changed.tags:
            findings.append({
                "id": "deleted_migration",
                "severity": "high",
                "path": changed.path,
                "message": "A migration file is deleted; verify deploy ordering and rollback safety.",
            })

    all_tags = sorted({tag for changed in files for tag in changed.tags})
    return DiffFacts(
        files=files,
        additions=sum(item.additions for item in files),
        deletions=sum(item.deletions for item in files),
        binary_files=sum(item.binary for item in files),
        test_files=sum("test" in item.tags for item in files),
        code_files=sum("code" in item.tags for item in files),
        tags=all_tags,
        deterministic_findings=findings,
    )


def chunk_diff(facts: DiffFacts, max_chars: int) -> list[DiffChunk]:
    chunks: list[DiffChunk] = []
    for changed in facts.files:
        pieces: list[str] = []
        buffer = ""
        hunks = changed.hunks or (["(binary file changed)"] if changed.binary else ["(metadata-only change)"])
        for hunk in hunks:
            if len(hunk) <= max_chars and len(buffer) + len(hunk) + 1 <= max_chars:
                buffer = f"{buffer}\n{hunk}".strip()
                continue
            if buffer:
                pieces.append(buffer)
                buffer = ""
            if len(hunk) <= max_chars:
                buffer = hunk
            else:
                lines = hunk.splitlines()
                segment = ""
                for line in lines:
                    if segment and len(segment) + len(line) + 1 > max_chars:
                        pieces.append(segment)
                        segment = ""
                    segment = f"{segment}\n{line}".strip()
                if segment:
                    pieces.append(segment)
        if buffer:
            pieces.append(buffer)
        for index, patch in enumerate(pieces, 1):
            chunks.append(DiffChunk(
                path=changed.path,
                index=index,
                total_for_file=len(pieces),
                patch=patch,
                file_facts={
                    "status": changed.status,
                    "additions": changed.additions,
                    "deletions": changed.deletions,
                    "binary": changed.binary,
                    "tags": changed.tags,
                },
            ))
    return chunks
