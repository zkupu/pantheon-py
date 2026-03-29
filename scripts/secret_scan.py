#!/usr/bin/env python3
"""Scan a tree for likely secrets and dangerous dynamic-execution patterns."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_EXCLUDES = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "results",
    "results-local",
}

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("gitlab-pat", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "inline-secret",
        re.compile(
            r"(?i)\b[A-Za-z0-9_]*(?:api[_-]?key|token|secret|password)[A-Za-z0-9_]*\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-/.+=]{8,}"
        ),
    ),
    ("dynamic-exec", re.compile(r"\b(?:eval|exec)\s*\(")),
]


@dataclass
class Finding:
    kind: str
    path: str
    line: int
    preview: str


def should_skip(path: Path, excludes: set[str]) -> bool:
    parts = set(path.parts)
    if parts & excludes:
        return True
    return any(
        fnmatch.fnmatch(path.as_posix(), pattern)
        for pattern in excludes
        if any(ch in pattern for ch in "*?[]")
    )


def is_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:4096]
    except OSError:
        return True
    return b"\x00" in chunk


def redact_preview(text: str) -> str:
    text = re.sub(
        r"\bglpat-[A-Za-z0-9_-]{8,}\b",
        lambda match: f"{match.group(0)[:4]}...{match.group(0)[-4:]}",
        text,
    )
    text = re.sub(
        r"\bsk-[A-Za-z0-9]{8,}\b",
        lambda match: f"{match.group(0)[:4]}...{match.group(0)[-4:]}",
        text,
    )
    text = re.sub(
        r"([=:]\s*['\"]?)([A-Za-z0-9_\-/.+=]{8,})",
        lambda match: f"{match.group(1)}{match.group(2)[:4]}...{match.group(2)[-4:]}",
        text,
    )
    return text.strip()


def scan_file(path: Path) -> list[Finding]:
    if is_binary(path):
        return []

    findings: list[Finding] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []

    for line_no, line in enumerate(lines, start=1):
        for kind, pattern in PATTERNS:
            if pattern.search(line):
                findings.append(
                    Finding(
                        kind=kind,
                        path=str(path),
                        line=line_no,
                        preview=redact_preview(line),
                    )
                )
    return findings


def scan_tree(root: Path, *, excludes: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or should_skip(path, excludes):
            continue
        findings.extend(scan_file(path))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan a tree for likely secrets")
    parser.add_argument("path", nargs="?", default=".", help="Root path to scan")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Exclude directory names or glob patterns; may be passed multiple times",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    excludes = DEFAULT_EXCLUDES | set(args.exclude)
    findings = scan_tree(root, excludes=excludes)

    if args.json:
        print(json.dumps([asdict(finding) for finding in findings], indent=2))
    else:
        for finding in findings:
            rel_path = Path(finding.path)
            try:
                rel_path = rel_path.relative_to(root)
            except ValueError:
                pass
            print(f"{finding.kind}: {rel_path}:{finding.line}: {finding.preview}")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
