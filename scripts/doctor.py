#!/usr/bin/env python3
"""Workspace doctor for Pantheon development environments."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from pantheon.config import repo_root  # noqa: E402


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def load_env_file(root: Path | None) -> Path | None:
    """Load the repo .env file into the process environment when present."""
    if root is None:
        return None

    env_path = root / ".env"
    if not env_path.exists():
        return env_path

    from pantheon.config import parse_env_file

    for key, value in parse_env_file(env_path).items():
        if key and not os.environ.get(key):
            os.environ[key] = value

    return env_path


def check_repo_root(root: Path | None) -> CheckResult:
    if root is None:
        return CheckResult("repo-root", "fail", "could not locate the Pantheon repository root")
    return CheckResult("repo-root", "ok", str(root))


def check_env_file(root: Path | None) -> CheckResult:
    if root is None:
        return CheckResult("env-file", "fail", "cannot check .env without a repository root")

    env_path = root / ".env"
    if env_path.exists():
        return CheckResult("env-file", "ok", str(env_path))
    return CheckResult("env-file", "warn", f"missing {env_path}")


def check_import_resolution(root: Path | None) -> CheckResult:
    if root is None:
        return CheckResult(
            "import-resolution",
            "fail",
            "cannot verify imports without a repository root",
        )

    src_dir = root / "src"
    init_py = src_dir / "pantheon" / "__init__.py"
    if not init_py.exists():
        return CheckResult("import-resolution", "fail", f"missing {init_py}")

    existing_module = sys.modules.pop("pantheon", None)
    sys.path.insert(0, str(src_dir))
    try:
        module = importlib.import_module("pantheon")
        module_path = Path(module.__file__ or "").resolve()
        if module_path != init_py.resolve():
            return CheckResult(
                "import-resolution",
                "warn",
                f"'pantheon' resolved to {module_path}, expected {init_py.resolve()}",
            )
        return CheckResult("import-resolution", "ok", str(module_path))
    except Exception as exc:  # pragma: no cover - defensive script path
        return CheckResult(
            "import-resolution",
            "fail",
            f"unable to import pantheon from {src_dir}: {exc}",
        )
    finally:
        sys.path.pop(0)
        sys.modules.pop("pantheon", None)
        if existing_module is not None:
            sys.modules["pantheon"] = existing_module


def check_command(name: str, *, required: bool) -> CheckResult:
    resolved = shutil.which(name)
    if resolved:
        return CheckResult(f"cmd:{name}", "ok", resolved)
    status = "fail" if required else "warn"
    return CheckResult(f"cmd:{name}", status, f"'{name}' is not available on PATH")


def check_env_var(name: str, *, required: bool) -> CheckResult:
    value = os.environ.get(name, "")
    if value:
        preview = "[set]" if len(value) <= 8 else f"{value[:4]}...{value[-4:]}"
        return CheckResult(f"env:{name.lower()}", "ok", preview)
    status = "fail" if required else "warn"
    return CheckResult(f"env:{name.lower()}", status, f"{name} is not set")


def check_protocol_consistency(root: Path | None) -> list[CheckResult]:
    """Check that key protocol elements are consistent across files."""
    if root is None:
        return [
            CheckResult(
                "protocol-root",
                "fail",
                "cannot check protocol without a repository root",
            )
        ]

    results: list[CheckResult] = []
    import re as _re

    agents_path = root / "AGENTS.md"
    claude_path = root / "CLAUDE.md"

    if not agents_path.is_file() or not claude_path.is_file():
        results.append(
            CheckResult(
                "protocol-files",
                "fail",
                f"missing {'AGENTS.md' if not agents_path.is_file() else 'CLAUDE.md'}",
            )
        )
        return results

    agents_md = agents_path.read_text(encoding="utf-8")
    claude_md = claude_path.read_text(encoding="utf-8")

    agents_thresholds = set(_re.findall(r"~?(\d+)\+?\s+turns", agents_md))
    claude_thresholds = set(_re.findall(r"~?(\d+)\+?\s+turns", claude_md))
    consistent = agents_thresholds == claude_thresholds
    results.append(
        CheckResult(
            "turn-thresholds",
            "ok" if consistent else "fail",
            f"AGENTS.md: {sorted(agents_thresholds)}, CLAUDE.md: {sorted(claude_thresholds)}",
        )
    )

    steps = ["Assess", "Activate", "Plan", "Execute", "Verify", "Report"]
    for step in steps:
        in_agents = step in agents_md
        in_claude = step in claude_md
        results.append(
            CheckResult(
                f"protocol-step-{step.lower()}",
                "ok" if in_agents and in_claude else "fail",
                f"AGENTS.md: {in_agents}, CLAUDE.md: {in_claude}",
            )
        )

    agents_count = _re.search(r"(\w+) agents are available as subagents", agents_md)
    claude_count = _re.search(r"(\w+) agents are available as subagents", claude_md)
    if agents_count and claude_count:
        consistent = agents_count.group(1) == claude_count.group(1)
        results.append(
            CheckResult(
                "subagent-count",
                "ok" if consistent else "fail",
                f"AGENTS.md: {agents_count.group(1)}, CLAUDE.md: {claude_count.group(1)}",
            )
        )

    return results


def check_claude_code(root: Path | None) -> list[CheckResult]:
    """Validate Claude Code readiness."""
    if root is None:
        return [CheckResult("repo-root", "fail", "could not locate the Pantheon repository root")]

    results: list[CheckResult] = []

    claude_md = root / "CLAUDE.md"
    cl_exists = claude_md.is_file()
    has_bootstrap = cl_exists and "Bootstrap" in claude_md.read_text(encoding="utf-8")
    results.append(
        CheckResult(
            "claude-md",
            "ok" if cl_exists and has_bootstrap else "fail",
            str(claude_md)
            if cl_exists and has_bootstrap
            else f"missing or incomplete {claude_md}",
        )
    )

    agents_md = root / "AGENTS.md"
    ag_exists = agents_md.is_file()
    has_roster = ag_exists and "demeter" in agents_md.read_text(encoding="utf-8").lower()
    results.append(
        CheckResult(
            "agents-md",
            "ok" if ag_exists and has_roster else "fail",
            str(agents_md) if ag_exists and has_roster else f"missing or incomplete {agents_md}",
        )
    )

    skills_dir = root / ".agents" / "skills"
    skill_count = len(list(skills_dir.glob("*/SKILL.md"))) if skills_dir.is_dir() else 0
    results.append(
        CheckResult(
            "skills",
            "ok" if skill_count >= 24 else "fail",
            f"{skill_count}/24 present in {skills_dir}",
        )
    )

    subagents_dir = root / ".agents" / "subagents"
    sub_count = len(list(subagents_dir.glob("*.md"))) if subagents_dir.is_dir() else 0
    results.append(
        CheckResult(
            "subagents",
            "ok" if sub_count >= 10 else "fail",
            f"{sub_count}/10 present in {subagents_dir}",
        )
    )

    env_file = root / ".env"
    env_exists = env_file.is_file()
    has_key = False
    if env_exists:
        content = env_file.read_text(encoding="utf-8")
        has_key = "INFERENCE_API_KEY" in content and "your-key" not in content
    results.append(
        CheckResult(
            "env-api-key",
            "ok" if env_exists and has_key else "warn",
            str(env_file)
            if env_exists and has_key
            else f"INFERENCE_API_KEY not configured in {env_file}",
        )
    )

    cursor_refs = []
    skills_dir = root / ".agents" / "skills"
    if skills_dir.is_dir():
        for skill_md in skills_dir.glob("*/SKILL.md"):
            content = skill_md.read_text(encoding="utf-8")
            if ".cursor/mcp.json" in content or "In Cursor," in content:
                cursor_refs.append(skill_md.parent.name)

    if cursor_refs:
        results.append(
            CheckResult(
                "no-cursor-deps",
                "warn",
                f"Skills with Cursor references: {', '.join(sorted(cursor_refs))}"
                " — these skills mention Cursor-specific features"
                " (fallback scripts exist, but instructions may confuse Claude Code)",
            )
        )
    else:
        results.append(
            CheckResult("no-cursor-deps", "ok", "No Cursor-specific references in skills")
        )

    init_py = root / "src" / "pantheon" / "__init__.py"
    results.append(
        CheckResult(
            "pantheon-source",
            "ok" if init_py.exists() else "fail",
            str(init_py) if init_py.exists() else f"missing {init_py}",
        )
    )

    is_linux = platform.system() == "Linux"
    on_mnt = str(root).startswith("/mnt/")
    if is_linux and on_mnt:
        results.append(
            CheckResult("filesystem", "warn", "repo on /mnt/ — move to ~/... for better I/O")
        )
    else:
        results.append(CheckResult("filesystem", "ok", f"native filesystem: {root}"))

    return results


def run_checks(
    *,
    root: Path | None,
    require_gateway: bool,
    require_skillgrade: bool,
) -> list[CheckResult]:
    """Run the doctor checks and return the outcomes."""
    load_env_file(root)
    results = [
        check_repo_root(root),
        check_env_file(root),
        check_import_resolution(root),
        check_command("python", required=True),
        check_command("git", required=True),
        check_command("ruff", required=False),
        check_command("pytest", required=False),
        check_command("skillgrade", required=require_skillgrade),
        check_env_var("INFERENCE_API_KEY", required=require_gateway),
    ]
    return results


def render_text(results: list[CheckResult]) -> str:
    lines = []
    for result in results:
        marker = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}[result.status]
        lines.append(f"[{marker}] {result.name}: {result.detail}")
    return "\n".join(lines)


def exit_code(results: list[CheckResult]) -> int:
    return 1 if any(result.status == "fail" for result in results) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pantheon workspace health checks")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("check", help="Run repository health checks")
    p.add_argument("--require-gateway", action="store_true", help="Require INFERENCE_API_KEY")
    p.add_argument("--require-skillgrade", action="store_true", help="Require the skillgrade CLI")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    cc = sub.add_parser("claude-code", help="Validate Claude Code readiness")
    cc.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    pr = sub.add_parser("protocol", help="Check protocol consistency across files")
    pr.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    au = sub.add_parser("audit", help="Verify audit chain integrity")
    au.add_argument("--path", default=None, help="Path to audit log file")
    au.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    args = parser.parse_args(argv)

    if args.command == "check":
        root = repo_root()
        results = run_checks(
            root=root,
            require_gateway=args.require_gateway,
            require_skillgrade=args.require_skillgrade,
        )
    elif args.command == "claude-code":
        root = repo_root()
        results = check_claude_code(root)
    elif args.command == "protocol":
        root = repo_root()
        results = check_protocol_consistency(root)
    elif args.command == "audit":
        root = repo_root()
        if root is not None:
            src_dir = str(root / "src")
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)

        from pantheon.tools import verify_audit_chain

        if args.path:
            audit_path = Path(args.path)
        elif root:
            audit_path = root / ".audit" / "tool-calls.jsonl"
        else:
            audit_path = None

        valid, issues = verify_audit_chain(audit_path)

        if args.json:
            print(json.dumps({"valid": valid, "issues": issues}, indent=2))
        else:
            if valid and not issues:
                print("[OK] audit chain: all entries verified")
            elif valid and issues:
                for issue in issues:
                    print(f"[INFO] {issue}")
            else:
                print(f"[FAIL] audit chain: {len(issues)} issue(s) found")
                for issue in issues:
                    print(f"  - {issue}")
        return 0 if valid else 1
    else:
        parser.print_help()
        return 1

    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
    else:
        print(render_text(results))
    return exit_code(results)


if __name__ == "__main__":
    raise SystemExit(main())
