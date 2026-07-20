"""Fail CI when a repository text file appears to contain a credential.

The scanner reports only file paths and rule names.  It never echoes a matched
value, which keeps a failing log from becoming a second disclosure channel.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".cjs", ".css", ".env", ".example", ".ini", ".js", ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml",
}
RULES = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_style_key": re.compile(r"\b(?:sk|rk|ds)-[A-Za-z0-9_-]{20,}\b"),
    "bearer_token": re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+[A-Za-z0-9._-]{16,}"),
    "assigned_secret": re.compile(
        r"(?i)\b(?:api[_-]?key|secret)\b\s*[:=]\s*[\"']?(?!<|your[_-]|example|changeme|\$\{|\{\{)[A-Za-z0-9._/-]{20,}"
    ),
    "database_url": re.compile(
        r"(?i)\b(?:database_url|migration_database_url|connection_string)\b\s*[:=]\s*[\"']?(?!<|your[_-]|example|\$\{|\{\{)(?:postgres|mysql|mongodb)://[^\s\"']+"
    ),
}


def main() -> int:
    paths = _workspace_files()
    findings: list[tuple[str, str]] = []
    for relative_path in paths:
        path = ROOT_DIR / relative_path
        if not _should_scan(path):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for rule_name, pattern in RULES.items():
            if pattern.search(content):
                findings.append((relative_path, rule_name))
    if not findings:
        print("Sensitive-content scan passed for repository text files.")
        return 0
    for relative_path, rule_name in findings:
        print(f"Sensitive-content scan failed: {relative_path} [{rule_name}]")
    return 1


def _workspace_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT_DIR,
        capture_output=True,
        check=True,
    )
    return [item for item in completed.stdout.decode("utf-8").split("\0") if item]


def _should_scan(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and ".git" not in path.parts


if __name__ == "__main__":
    sys.exit(main())
