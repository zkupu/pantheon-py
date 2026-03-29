#!/usr/bin/env python3
"""Skill improvement pipeline — diagnose eval failures and propose SKILL.md changes.

Reads eval results from the results/ directory, diagnoses failure patterns,
and optionally calls the NIM API to propose concrete SKILL.md improvements.
With --apply, rewrites the SKILL.md files in place.

Usage:
    python evals/bin/improve.py results/                          # Diagnose only
    python evals/bin/improve.py results/ --propose                # + LLM proposals
    python evals/bin/improve.py results/ --propose --apply        # + rewrite SKILL.md files
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pantheon.gateway import Client, Message  # noqa: E402
from pantheon.skill import split_frontmatter  # noqa: E402

# ── Diagnosis ────────────────────────────────────────────────


def parse_check_lines(details: str) -> list[dict]:
    """Extract per-check pass/fail from deterministic grader details."""
    checks = []
    for m in re.finditer(r"(\u2713|\u2717)\s+(\S+):\s*(.*)", details):
        checks.append({
            "name": m.group(2),
            "passed": m.group(1) == "\u2713",
            "message": m.group(3).strip(),
        })
    return checks


def diagnose_skill(
    skill_name: str,
    result_files: list[Path],
    threshold: float,
) -> dict:
    """Analyze all eval results for a skill and produce a structured diagnosis."""
    all_trials: list[dict] = []
    all_tasks: list[dict] = []

    for f in result_files:
        report = json.loads(f.read_text())
        trials = report.get("trials", [])
        all_trials.extend(trials)

        check_stats: dict[str, dict] = {}
        rubric_feedback: list[str] = []

        for trial in trials:
            for gr in trial.get("grader_results", []):
                if gr["grader_type"] == "deterministic":
                    for c in parse_check_lines(gr.get("details", "")):
                        entry = check_stats.setdefault(
                            c["name"], {"passed": 0, "failed": 0, "messages": []}
                        )
                        if c["passed"]:
                            entry["passed"] += 1
                        else:
                            entry["failed"] += 1
                            entry["messages"].append(c["message"])

                elif gr["grader_type"] == "llm_rubric":
                    text = gr.get("details", "")
                    if text and not text.startswith("Failed to parse"):
                        rubric_feedback.append(text)

        command_counts = [t.get("n_commands", 0) for t in trials]
        durations = [t.get("duration_ms", 0) / 1000 for t in trials]
        rewards = [t.get("reward", 0) for t in trials]

        all_tasks.append({
            "name": report["task"],
            "pass_rate": round(report.get("pass_rate", 0), 3),
            "pass_at_k": round(report.get("pass_at_k", 0), 3),
            "pass_pow_k": round(report.get("pass_pow_k", 0), 3),
            "num_trials": len(trials),
            "num_passed": sum(1 for r in rewards if r >= 0.5),
            "check_failures": {
                name: {
                    "failure_rate": round(
                        s["failed"] / max(s["passed"] + s["failed"], 1), 2
                    ),
                    "count": s["failed"],
                    "total": s["passed"] + s["failed"],
                    "sample_messages": list(set(s["messages"]))[:3],
                }
                for name, s in check_stats.items()
                if s["failed"] > 0
            },
            "rubric_feedback": rubric_feedback,
            "behavior": {
                "avg_commands": round(
                    sum(command_counts) / max(len(command_counts), 1), 1
                ),
                "min_commands": min(command_counts) if command_counts else 0,
                "max_commands": max(command_counts) if command_counts else 0,
                "avg_duration_s": round(
                    sum(durations) / max(len(durations), 1), 1
                ),
            },
        })

    total_trials = len(all_trials)
    overall = (
        sum(t.get("reward", 0) for t in all_trials) / max(total_trials, 1)
    )

    return {
        "skill": skill_name,
        "skill_path": f".agents/skills/{skill_name}",
        "overall_pass_rate": round(overall, 3),
        "total_trials": total_trials,
        "total_passed": sum(1 for t in all_trials if t.get("reward", 0) >= 0.5),
        "below_threshold": overall < threshold,
        "tasks": all_tasks,
    }


# ── LLM Proposals ───────────────────────────────────────────


def _format_diagnosis(d: dict) -> str:
    """Format a diagnosis dict into readable text for the LLM prompt."""
    lines: list[str] = []
    for task in d["tasks"]:
        lines.append(f"### Task: {task['name']}")
        lines.append(
            f"Pass rate: {task['pass_rate']:.0%} "
            f"({task['num_passed']}/{task['num_trials']} trials)"
        )
        b = task["behavior"]
        lines.append(
            f"Behavior: avg {b['avg_commands']:.0f} commands, "
            f"{b['avg_duration_s']:.0f}s duration"
        )

        if task["check_failures"]:
            lines.append("\nFailing deterministic checks:")
            for name, info in task["check_failures"].items():
                lines.append(
                    f"  - {name}: failed {info['count']}/{info['total']} times"
                )
                for msg in info["sample_messages"]:
                    lines.append(f"    \u2192 {msg}")

        if task["rubric_feedback"]:
            lines.append("\nLLM rubric feedback (from grading sessions):")
            for fb in task["rubric_feedback"][:3]:
                lines.append(f"  - {fb[:300]}")

        lines.append("")
    return "\n".join(lines)


_PROMPT_TEMPLATE = """\
You are a skill improvement analyst for the Pantheon \u2014 a team of AI agent specialists.

A "skill" is a SKILL.md file (YAML frontmatter + Markdown body) that becomes an agent's
system prompt. When an agent receives a task, the skill's content shapes how it thinks and acts.
Skillgrade evaluations test whether agents using these skills complete realistic tasks correctly.

Below is the current SKILL.md and evaluation results showing where the agent struggles.

## Current SKILL.md

```markdown
{skill_content}
```

## Evaluation Results

Overall pass rate: {pass_rate:.0%} ({passed}/{total} trials)

{diagnosis_text}

## Your Task

Analyze the failure patterns and propose specific, targeted changes to the SKILL.md that
would improve performance. Focus on:

1. Missing instructions the agent clearly needs (e.g., "always verify output files exist")
2. Strengthening verification/validation steps
3. Clarifying ambiguous methodology
4. Adding explicit handling for common failure modes
5. Removing contradictory or unhelpful guidance

Do NOT propose cosmetic rewording. Only propose changes that directly address observed failures.

Return ONLY a JSON object (no markdown fences):
{{
  "summary": "1-2 sentence diagnosis of the core issues",
  "root_causes": ["cause1", "cause2"],
  "proposals": [
    {{
      "section": "Which section of the SKILL.md to modify or add",
      "action": "add|modify|remove",
      "description": "What to change and why it fixes the observed failure",
      "suggested_text": "Exact markdown text to add or replace with",
      "priority": "high|medium|low"
    }}
  ]
}}"""


def propose_improvements(diagnosis: dict, skill_content: str) -> dict | None:
    """Call NIM API to propose SKILL.md improvements based on diagnosis."""
    prompt = _PROMPT_TEMPLATE.format(
        skill_content=skill_content,
        pass_rate=diagnosis["overall_pass_rate"],
        passed=diagnosis["total_passed"],
        total=diagnosis["total_trials"],
        diagnosis_text=_format_diagnosis(diagnosis),
    )

    text = _nim_chat(prompt, max_tokens=4096)
    if text is None:
        print("  \u26a0 LLM unavailable \u2014 skipping proposals", file=sys.stderr)
        return None

    try:
        cleaned = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            return json.loads(m.group(0))
        return {"error": f"Could not parse JSON from LLM response: {text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


# ── Apply Rewrites ───────────────────────────────────────────


_REWRITE_TEMPLATE = """\
You are improving a SKILL.md file for an AI agent in the Pantheon system.

The SKILL.md format is YAML frontmatter (between --- delimiters) followed by a Markdown body.
The Markdown body becomes the agent's system prompt during task execution.

Below is the current file, evaluation failures, and proposed improvements.

RULES:
- Preserve the YAML frontmatter EXACTLY as-is (name, description, metadata, etc.)
- Only modify the Markdown body (everything after the closing ---)
- Incorporate the proposed improvements naturally into the existing structure
- Keep the same voice, tone, and organizational structure as the original
- Be surgical: make the minimum changes needed to address the observed failures
- Do NOT add filler, disclaimers, or meta-commentary about the changes
- Do NOT wrap your output in markdown fences

## Current SKILL.md

{skill_content}

## Evaluation Failures

Overall pass rate: {pass_rate:.0%} ({passed}/{total} trials)

{diagnosis_text}

## Proposed Improvements

{proposals_text}

Now output the complete improved SKILL.md (frontmatter + body), nothing else:"""


def _format_proposals(proposals: dict) -> str:
    if not proposals or "error" in proposals:
        return "No structured proposals available."
    lines: list[str] = []
    if proposals.get("summary"):
        lines.append(f"Summary: {proposals['summary']}")
    if proposals.get("root_causes"):
        lines.append("\nRoot causes:")
        for c in proposals["root_causes"]:
            lines.append(f"  - {c}")
    if proposals.get("proposals"):
        lines.append("\nChanges:")
        for p in proposals["proposals"]:
            prio = p.get("priority", "medium")
            lines.append(
                f"  - [{prio}] {p.get('section', '?')}: "
                f"{p.get('description', '?')}"
            )
            if p.get("suggested_text"):
                lines.append(f"    Text: {p['suggested_text'][:200]}")
    return "\n".join(lines)


def _nim_chat(prompt: str, max_tokens: int = 8192) -> str | None:
    """Call NIM API and return the response text, or None on failure."""
    api_key = os.environ.get("NIM_API_KEY") or os.environ.get("INFERENCE_API_KEY")
    base_url = os.environ.get("NIM_BASE_URL") or os.environ.get("GATEWAY_URL", "")
    model = os.environ.get("NIM_MODEL", "azure/openai/gpt-4.1-mini")
    if not api_key:
        return None

    try:
        with Client(base_url, api_key, timeout=180) as client:
            resp = client.chat(
                model=model,
                messages=[Message(role="user", content=prompt)],
                temperature=0.2,
                max_tokens=max_tokens,
            )
        return resp.content
    except Exception as e:
        print(f"    LLM call failed: {e}", file=sys.stderr)
        return None


_DANGEROUS_PATTERNS = [
    r"shell_exec\s*\(",
    r"subprocess\.\w+\(",
    r"os\.system\s*\(",
    r"eval\s*\(",
    r"exec\s*\(",
    r"rm\s+-rf\b",
    r"curl\s+.*\|.*(?:sh|bash)",
    r"wget\s+.*\|.*(?:sh|bash)",
    r"(?:https?://)\S+\.(?:sh|exe|bat|cmd|ps1)\b",
    r"base64\s+(?:--decode|-d)",
    r"IGNORE\s+(?:ALL\s+)?PREVIOUS\s+INSTRUCTIONS",
    r"ignore\s+(?:all\s+)?previous\s+instructions",
]


def _validate_skill_content(content: str, original: str) -> str | None:
    """Validate rewritten SKILL.md. Returns error message or None if valid."""
    if not content.strip():
        return "Empty output"

    new_frontmatter, body = split_frontmatter(content)
    if not new_frontmatter:
        return "Missing YAML frontmatter"

    try:
        import yaml
        front = yaml.safe_load(new_frontmatter)
        if not isinstance(front, dict):
            return "Frontmatter is not a YAML mapping"
    except Exception as e:
        return f"Frontmatter YAML parse error: {e}"

    if len(body) < 50:
        return f"Body too short ({len(body)} chars)"

    original_frontmatter, _ = split_frontmatter(original)
    if new_frontmatter != original_frontmatter:
        return "Frontmatter changed; only the Markdown body may be rewritten"

    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, body, re.IGNORECASE):
            return f"Dangerous pattern detected in body: {pattern}"

    orig_len = len(original.strip())
    new_len = len(content.strip())
    if orig_len > 0 and new_len > orig_len * 3:
        return (
            f"Rewrite suspiciously large: {new_len} chars vs "
            f"original {orig_len} chars ({new_len / orig_len:.1f}x)"
        )

    return None


def rewrite_skill(
    diagnosis: dict,
    proposals: dict | None,
    skill_content: str,
) -> str | None:
    """Call LLM to produce a complete rewritten SKILL.md."""
    prompt = _REWRITE_TEMPLATE.format(
        skill_content=skill_content,
        pass_rate=diagnosis["overall_pass_rate"],
        passed=diagnosis["total_passed"],
        total=diagnosis["total_trials"],
        diagnosis_text=_format_diagnosis(diagnosis),
        proposals_text=_format_proposals(proposals) if proposals else "N/A",
    )

    text = _nim_chat(prompt, max_tokens=8192)
    if not text:
        return None

    content = text.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:markdown|yaml)?\s*\n?", "", content)
        content = re.sub(r"\n?```\s*$", "", content)

    return content.strip()


# ── Markdown Report ──────────────────────────────────────────


def generate_report(
    diagnoses: list[dict],
    proposals: dict[str, dict | None],
    threshold: float,
) -> str:
    lines = [
        "# Pantheon Skill Improvement Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Threshold: {threshold:.0%}",
        "",
        "## Summary",
        "",
        "| Skill | Pass Rate | Trials | Status |",
        "|-------|-----------|--------|--------|",
    ]

    for d in sorted(diagnoses, key=lambda x: x["overall_pass_rate"]):
        status = (
            "\u2717 Below threshold" if d["below_threshold"] else "\u2713 Pass"
        )
        lines.append(
            f"| {d['skill']} | {d['overall_pass_rate']:.0%} | "
            f"{d['total_trials']} | {status} |"
        )
    lines.append("")

    failing = [d for d in diagnoses if d["below_threshold"]]
    if not failing:
        lines.append("## All Skills Above Threshold \u2713")
        lines.append("")
        lines.append("No improvements needed at this time.")
        return "\n".join(lines)

    lines.append(f"## Skills Below Threshold ({len(failing)})")
    lines.append("")

    for d in sorted(failing, key=lambda x: x["overall_pass_rate"]):
        lines.append(f"### {d['skill']} \u2014 {d['overall_pass_rate']:.0%}")
        lines.append("")

        for task in d["tasks"]:
            lines.append(
                f"**Task: {task['name']}** \u2014 "
                f"{task['pass_rate']:.0%} ({task['num_passed']}/{task['num_trials']})"
            )
            lines.append("")

            if task["check_failures"]:
                lines.append("Failing checks:")
                for name, info in task["check_failures"].items():
                    lines.append(
                        f"- **{name}**: failed {info['count']}/{info['total']}"
                    )
                    for msg in info["sample_messages"]:
                        lines.append(f"  - {msg}")
                lines.append("")

            if task["rubric_feedback"]:
                lines.append("Rubric feedback:")
                for fb in task["rubric_feedback"][:3]:
                    lines.append(f"- {fb[:300]}")
                lines.append("")

            b = task["behavior"]
            lines.append(
                f"Agent behavior: {b['avg_commands']:.0f} avg commands "
                f"({b['min_commands']}\u2013{b['max_commands']}), "
                f"{b['avg_duration_s']:.0f}s avg"
            )
            lines.append("")

        skill_prop = proposals.get(d["skill"])
        if skill_prop and "error" not in skill_prop:
            lines.append("#### Proposed Improvements")
            lines.append("")
            lines.append(
                f"**Diagnosis:** {skill_prop.get('summary', 'N/A')}"
            )
            lines.append("")

            if skill_prop.get("root_causes"):
                lines.append("**Root causes:**")
                for cause in skill_prop["root_causes"]:
                    lines.append(f"- {cause}")
                lines.append("")

            if skill_prop.get("proposals"):
                for i, p in enumerate(skill_prop["proposals"], 1):
                    prio = p.get("priority", "medium").upper()
                    section = p.get("section", "N/A")
                    action = p.get("action", "modify")
                    desc = p.get("description", "N/A")
                    lines.append(f"{i}. **[{prio}]** {section} \u2014 {action}")
                    lines.append(f"   {desc}")
                    if p.get("suggested_text"):
                        lines.append("")
                        lines.append("   ```markdown")
                        for line in p["suggested_text"].splitlines():
                            lines.append(f"   {line}")
                        lines.append("   ```")
                    lines.append("")

        elif skill_prop and "error" in skill_prop:
            lines.append(f"*LLM proposal failed: {skill_prop['error']}*")
            lines.append("")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────


def find_result_files(results_dir: Path) -> dict[str, list[Path]]:
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze eval results and propose skill improvements",
    )
    parser.add_argument("results_dir", type=Path, help="Path to results/ directory")
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=Path(".agents/skills"),
        help="Path to skills directory (default: .agents/skills)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Pass rate threshold (default: 0.5)",
    )
    parser.add_argument(
        "--propose",
        action="store_true",
        help="Call NIM API to propose SKILL.md improvements",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite SKILL.md files in place (implies --propose)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: <results_dir>/improvements)",
    )
    args = parser.parse_args()
    if args.apply:
        args.propose = True

    results_dir: Path = args.results_dir
    skills_dir: Path = args.skills_dir
    output_dir: Path = args.output or results_dir / "improvements"

    skill_files = find_result_files(results_dir)
    if not skill_files:
        print(f"No eval results found in {results_dir}", file=sys.stderr)
        sys.exit(1)

    # ── Diagnose ──────────────────────────────────────────
    diagnoses: list[dict] = []
    for skill_name, files in sorted(skill_files.items()):
        print(f"Diagnosing {skill_name}...", flush=True)
        d = diagnose_skill(skill_name, files, args.threshold)
        diagnoses.append(d)
        tag = "BELOW THRESHOLD" if d["below_threshold"] else "OK"
        print(f"  {d['overall_pass_rate']:.0%} \u2014 {tag}")

    # ── Propose (optional) ────────────────────────────────
    proposals: dict[str, dict | None] = {}
    if args.propose:
        failing = [d for d in diagnoses if d["below_threshold"]]
        if failing:
            print(f"\nProposing improvements for {len(failing)} skill(s)...")
            for d in failing:
                skill_path = skills_dir / d["skill"] / "SKILL.md"
                if not skill_path.exists():
                    print(f"  \u26a0 {skill_path} not found", file=sys.stderr)
                    proposals[d["skill"]] = {
                        "error": f"SKILL.md not found: {skill_path}",
                    }
                    continue
                print(f"  Calling LLM for {d['skill']}...", flush=True)
                proposals[d["skill"]] = propose_improvements(
                    d, skill_path.read_text()
                )
        else:
            print("\nAll skills above threshold \u2014 no proposals needed.")

    # ── Apply rewrites (optional) ────────────────────────
    applied: list[str] = []
    if args.apply:
        failing_with_proposals = [
            d for d in diagnoses
            if d["below_threshold"] and d["skill"] in proposals
            and proposals[d["skill"]] and "error" not in proposals[d["skill"]]
        ]
        if failing_with_proposals:
            print(f"\nApplying rewrites to {len(failing_with_proposals)} skill(s)...")
            for d in failing_with_proposals:
                skill_path = skills_dir / d["skill"] / "SKILL.md"
                if not skill_path.exists():
                    print(f"  \u26a0 {skill_path} not found", file=sys.stderr)
                    continue

                original = skill_path.read_text()
                print(f"  Rewriting {d['skill']}...", flush=True)
                rewritten = rewrite_skill(d, proposals[d["skill"]], original)

                if not rewritten:
                    print("    \u2717 LLM returned empty \u2014 skipped")
                    continue

                err = _validate_skill_content(rewritten, original)
                if err:
                    print(f"    \u2717 Validation failed: {err} \u2014 skipped")
                    continue

                skill_path.write_text(rewritten + "\n")
                applied.append(d["skill"])
                print(f"    \u2713 {skill_path}")
        else:
            print("\nNo skills eligible for rewrite.")

    # ── Write outputs ─────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)

    for d in diagnoses:
        out = dict(d)
        if d["skill"] in proposals:
            out["proposals"] = proposals[d["skill"]]
        out["applied"] = d["skill"] in applied
        (output_dir / f"{d['skill']}.json").write_text(
            json.dumps(out, indent=2) + "\n"
        )

    report = generate_report(diagnoses, proposals, args.threshold)
    (output_dir / "report.md").write_text(report + "\n")

    print(f"\nResults written to {output_dir}/")
    print("  report.md \u2014 human-readable improvement report")
    for d in diagnoses:
        suffix = ""
        if d["skill"] in applied:
            suffix = " (APPLIED)"
        elif d["skill"] in proposals:
            suffix = " + proposals"
        print(f"  {d['skill']}.json \u2014 diagnosis{suffix}")

    if applied:
        print(f"\n{len(applied)} SKILL.md file(s) rewritten: {', '.join(applied)}")

    below = [d for d in diagnoses if d["below_threshold"]]
    if below:
        print(
            f"\n{len(below)} skill(s) below {args.threshold:.0%} threshold",
        )


if __name__ == "__main__":
    main()
