#!/usr/bin/env python3
"""Validate Pantheon skill roster and script documentation consistency."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Finding:
    level: str
    scope: str
    message: str


def find_repo_root(start: str | Path | None = None) -> Path | None:
    current = Path(start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / ".agents" / "skills").is_dir():
            return candidate
    return None


def list_skill_names(root: Path) -> set[str]:
    skills_dir = root / ".agents" / "skills"
    return {
        entry.name
        for entry in skills_dir.iterdir()
        if entry.is_dir() and (entry / "SKILL.md").exists()
    }


def section_text(text: str, heading: str) -> str:
    pattern = re.compile(rf"^{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##+\s", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


def extract_first_column_names(table_section: str) -> set[str]:
    names: set[str] = set()
    for raw_line in table_section.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        first = cells[0]
        if first.lower() in {"agent", "name"}:
            continue
        if set(first) <= {"-", ":"}:
            continue
        if re.fullmatch(r"[a-z][a-z0-9_-]*", first):
            names.add(first)
    return names


def validate_roster_file(
    root: Path, relative_path: str, heading: str, expected: set[str]
) -> list[Finding]:
    path = root / relative_path
    text = path.read_text(encoding="utf-8")
    actual = extract_first_column_names(section_text(text, heading))

    findings: list[Finding] = []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        findings.append(
            Finding(
                "error",
                relative_path,
                f"missing skills in {heading}: {', '.join(missing)}",
            )
        )
    if extra:
        findings.append(
            Finding(
                "error",
                relative_path,
                f"unexpected roster entries in {heading}: {', '.join(extra)}",
            )
        )
    return findings


def validate_scripts_readme(root: Path) -> list[Finding]:
    scripts_dir = root / "scripts"
    readme_path = scripts_dir / "README.md"
    text = readme_path.read_text(encoding="utf-8")
    documented = set(re.findall(r"`([A-Za-z0-9_.-]+\.py)`", text))
    actual = {path.name for path in scripts_dir.glob("*.py")}

    findings: list[Finding] = []
    missing = sorted(actual - documented)
    stale = sorted(documented - actual)
    if missing:
        findings.append(
            Finding(
                "error",
                "scripts/README.md",
                f"missing script docs for: {', '.join(missing)}",
            )
        )
    if stale:
        findings.append(
            Finding(
                "error",
                "scripts/README.md",
                f"documents missing scripts: {', '.join(stale)}",
            )
        )
    return findings


def validate_eval_coverage(root: Path, skills: set[str]) -> list[Finding]:
    evals_dir = root / "evals"
    actual = {
        entry.name
        for entry in evals_dir.iterdir()
        if entry.is_dir() and entry.name != "_template" and (entry / "eval.yaml").exists()
    }
    missing = sorted(skills - actual)
    if not missing:
        return []
    return [Finding("warn", "evals", f"skills without eval coverage: {', '.join(missing)}")]


def run_validation(root: Path) -> list[Finding]:
    skills = list_skill_names(root)
    findings = []
    findings.extend(validate_roster_file(root, "README.md", "## The Pantheon", skills))
    findings.extend(validate_roster_file(root, "AGENTS.md", "## Roster", skills))
    findings.extend(validate_roster_file(root, ".cursor/rules/pantheon.mdc", "## Roster", skills))
    findings.extend(validate_scripts_readme(root))
    findings.extend(validate_eval_coverage(root, skills))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Pantheon repository consistency")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("validate", help="Validate rosters, scripts, and eval coverage")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    if args.command != "validate":
        parser.print_help()
        return 1

    root = find_repo_root()
    if root is None:
        finding = Finding("error", "repo", "could not locate the Pantheon repository root")
        payload = [asdict(finding)]
        print(
            json.dumps(payload, indent=2)
            if args.json
            else f"[ERROR] {finding.scope}: {finding.message}"
        )
        return 1

    findings = run_validation(root)
    if args.json:
        print(json.dumps([asdict(finding) for finding in findings], indent=2))
    else:
        if not findings:
            print("validation passed")
        for finding in findings:
            print(f"[{finding.level.upper()}] {finding.scope}: {finding.message}")

    return 1 if any(finding.level == "error" for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
