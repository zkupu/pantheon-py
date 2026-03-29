#!/usr/bin/env python3
"""Generate summary.json from skillgrade eval results.

Walks the results/ directory, parses every EvalReport JSON, and produces
a single summary.json that downstream jobs can consume without knowing
the directory structure.

Usage:
    python evals/bin/summarize.py results/
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def find_result_files(results_dir: Path) -> dict[str, list[Path]]:
    """Find all eval result JSON files grouped by skill name."""
    skills: dict[str, list[Path]] = {}
    for skill_dir in sorted(results_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        inner = skill_dir / "results"
        if not inner.is_dir():
            continue
        json_files = sorted(inner.glob("*.json"))
        if json_files:
            skills[skill_dir.name] = json_files
    return skills


def summarize(results_dir: Path) -> dict:
    skill_files = find_result_files(results_dir)
    skills: dict[str, dict] = {}

    for skill_name, files in sorted(skill_files.items()):
        tasks = []
        total_reward = 0.0
        total_trials = 0

        for f in files:
            report = json.loads(f.read_text())
            trials = report.get("trials", [])
            n = len(trials)
            if n == 0:
                continue

            passed = sum(1 for t in trials if t.get("reward", 0) >= 0.5)
            avg_dur = sum(t.get("duration_ms", 0) for t in trials) / n
            avg_cmds = sum(t.get("n_commands", 0) for t in trials) / n

            tasks.append({
                "name": report["task"],
                "pass_rate": round(report.get("pass_rate", 0), 3),
                "pass_at_k": round(report.get("pass_at_k", 0), 3),
                "pass_pow_k": round(report.get("pass_pow_k", 0), 3),
                "num_trials": n,
                "num_passed": passed,
                "avg_duration_s": round(avg_dur / 1000, 1),
                "avg_commands": round(avg_cmds, 1),
                "result_file": str(f.relative_to(results_dir)),
            })

            total_reward += report.get("pass_rate", 0) * n
            total_trials += n

        overall = round(total_reward / max(total_trials, 1), 3)
        skills[skill_name] = {
            "skill_path": f".agents/skills/{skill_name}",
            "overall_pass_rate": overall,
            "total_trials": total_trials,
            "tasks": tasks,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "num_skills": len(skills),
        "skills": skills,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: summarize.py <results-dir>", file=sys.stderr)
        sys.exit(1)

    results_dir = Path(sys.argv[1])
    if not results_dir.is_dir():
        print(f"Not a directory: {results_dir}", file=sys.stderr)
        sys.exit(1)

    summary = summarize(results_dir)
    out = results_dir / "summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")

    print(f"Summary written to {out}")
    print(f"Skills evaluated: {summary['num_skills']}")
    for name, data in sorted(
        summary["skills"].items(),
        key=lambda x: x[1]["overall_pass_rate"],
    ):
        rate = data["overall_pass_rate"]
        mark = "\u2713" if rate >= 0.5 else "\u2717"
        print(f"  {mark} {name}: {rate:.0%}")


if __name__ == "__main__":
    main()
