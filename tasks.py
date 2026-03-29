#!/usr/bin/env python3
"""Cross-platform task runner for Pantheon development.

Replaces the Makefile for Windows users. Unix users can continue using `make`.

Usage:
    python tasks.py install       # pip install .
    python tasks.py dev           # pip install -e ".[dev]"
    python tasks.py test          # pytest
    python tasks.py lint          # ruff check
    python tasks.py validate      # validate skill rosters
    python tasks.py doctor        # workspace health checks
    python tasks.py secret-scan   # scan for secrets
    python tasks.py check         # lint + validate + test
    python tasks.py clean         # remove build artifacts
    python tasks.py eval          # run all skillgrade evals
    python tasks.py eval-skill SKILL  # run one eval
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> int:
    merged_env = {**os.environ, **(env or {})}
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd or REPO_ROOT, env=merged_env)
    return result.returncode


def cmd_install() -> int:
    return run([PYTHON, "-m", "pip", "install", "."])


def cmd_dev() -> int:
    return run([PYTHON, "-m", "pip", "install", "-e", ".[dev]"])


def cmd_test() -> int:
    return run([PYTHON, "-m", "pytest", "tests/", "-v"])


def cmd_lint() -> int:
    return run([PYTHON, "-m", "ruff", "check", "src/", "tests/", "scripts/", ".agents/skills/"])


def cmd_validate() -> int:
    return run([PYTHON, "scripts/skill_validate.py", "validate"])


def cmd_doctor() -> int:
    return run([PYTHON, "scripts/doctor.py", "check"])


def cmd_secret_scan() -> int:
    return run([PYTHON, "scripts/secret_scan.py", "."])


def cmd_check() -> int:
    for fn in (cmd_lint, cmd_validate, cmd_test):
        rc = fn()
        if rc != 0:
            return rc
    return 0


def cmd_clean() -> int:
    dirs_to_remove = ["build", "dist", ".pytest_cache", ".cache"]
    for d in dirs_to_remove:
        target = REPO_ROOT / d
        if target.is_dir():
            print(f"  removing {target}")
            shutil.rmtree(target)

    for egg in REPO_ROOT.glob("*.egg-info"):
        print(f"  removing {egg}")
        shutil.rmtree(egg)

    for pycache in REPO_ROOT.rglob("__pycache__"):
        print(f"  removing {pycache}")
        shutil.rmtree(pycache)

    for pyc in REPO_ROOT.rglob("*.pyc"):
        print(f"  removing {pyc}")
        pyc.unlink()

    return 0


def _load_env_file() -> dict[str, str]:
    """Load .env file into a dict without mutating os.environ."""
    src_dir = str(REPO_ROOT / "src")
    inserted = False
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
        inserted = True
    try:
        from pantheon.config import parse_env_file

        return parse_env_file(REPO_ROOT / ".env")
    finally:
        if inserted:
            sys.path.remove(src_dir)


def cmd_eval(skill: str | None = None) -> int:
    evals_dir = REPO_ROOT / "evals"
    env_extra = _load_env_file()

    nim_key = env_extra.get("NIM_API_KEY") or env_extra.get("INFERENCE_API_KEY", "")
    nim_url = env_extra.get("NIM_BASE_URL") or env_extra.get("GATEWAY_URL", "")
    nim_model = env_extra.get("NIM_MODEL", "azure/openai/gpt-4.1-mini")

    eval_env = {
        **env_extra,
        "NIM_API_KEY": os.environ.get("NIM_API_KEY", nim_key),
        "NIM_BASE_URL": os.environ.get("NIM_BASE_URL", nim_url),
        "NIM_MODEL": os.environ.get("NIM_MODEL", nim_model),
        "XDG_CACHE_HOME": str(REPO_ROOT / ".cache"),
    }

    eval_path = str(REPO_ROOT / "evals" / "bin")
    eval_env["PATH"] = eval_path + os.pathsep + os.environ.get("PATH", "")

    results_dir = REPO_ROOT / "results"
    results_dir.mkdir(exist_ok=True)

    if skill:
        skills = [skill]
    else:
        skills = sorted(
            d.parent.name
            for d in evals_dir.glob("*/eval.yaml")
            if d.parent.name != "_template"
        )

    for s in skills:
        skill_dir = evals_dir / s
        if not (skill_dir / "eval.yaml").exists():
            print(f"  SKIP: evals/{s}/eval.yaml not found")
            continue
        print(f"=== eval: {s} ===")
        rc = run(
            ["skillgrade", "--smoke", "--provider=local", f"--output={results_dir}"],
            cwd=skill_dir,
            env=eval_env,
        )
        if rc != 0:
            print(f"  eval {s} failed with exit code {rc}")
            return rc

    run([PYTHON, "evals/bin/summarize.py", str(results_dir) + "/"])
    return 0


COMMANDS = {
    "install": cmd_install,
    "dev": cmd_dev,
    "test": cmd_test,
    "lint": cmd_lint,
    "validate": cmd_validate,
    "doctor": cmd_doctor,
    "secret-scan": cmd_secret_scan,
    "check": cmd_check,
    "clean": cmd_clean,
    "eval": cmd_eval,
    "eval-skill": None,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("Commands:", ", ".join(sorted(COMMANDS)))
        return 0

    command = sys.argv[1]

    if command == "eval-skill":
        if len(sys.argv) < 3:
            print("Usage: python tasks.py eval-skill SKILL_NAME")
            return 1
        return cmd_eval(skill=sys.argv[2])

    if command == "eval":
        return cmd_eval()

    fn = COMMANDS.get(command)
    if fn is None:
        print(f"Unknown command: {command}")
        print("Commands:", ", ".join(sorted(COMMANDS)))
        return 1

    return fn()


if __name__ == "__main__":
    raise SystemExit(main())
