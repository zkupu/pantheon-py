"""SKILL.md parser following the agentskills.io specification."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_log = logging.getLogger(__name__)


@dataclass
class Metadata:
    """SKILL.md frontmatter fields controlling agent behavior.

    Parsed from the YAML block at the top of a SKILL.md file. Fields
    like model, temperature, and tools configure the agent's runtime.
    """

    persona: str = ""
    model: str = ""
    temperature: float | None = None
    max_tokens: int = 0
    max_iterations: int = 0
    tools: list[str] = field(default_factory=list)
    delegates: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    routing_signals: list[str] = field(default_factory=list)
    boost_signals: list[str] = field(default_factory=list)


@dataclass
class Skill:
    """Parsed representation of a SKILL.md agent definition.

    Contains the agent's identity (name, description, persona), runtime
    configuration (model, tools, limits), and instruction body.
    """

    name: str
    description: str
    body: str
    path: str
    license: str = ""
    compatibility: list[str] = field(default_factory=list)
    metadata: Metadata = field(default_factory=Metadata)

    @property
    def persona(self) -> str:
        return self.metadata.persona

    @property
    def model(self) -> str:
        return self.metadata.model or "meta/llama-3.3-70b-instruct"

    @property
    def temperature(self) -> float:
        if self.metadata.temperature is not None:
            return self.metadata.temperature
        return 0.7

    @property
    def max_tokens(self) -> int:
        return self.metadata.max_tokens or 4096

    @property
    def max_iterations(self) -> int:
        return self.metadata.max_iterations or 10

    @property
    def tool_names(self) -> list[str]:
        return self.metadata.tools

    @property
    def delegate_names(self) -> list[str]:
        return self.metadata.delegates

    @property
    def allowed_tool_names(self) -> list[str]:
        return self.metadata.allowed_tools

    @property
    def routing_signals(self) -> list[str]:
        return self.metadata.routing_signals

    @property
    def catalog_entry(self) -> dict[str, str]:
        """Tier-1 progressive disclosure: lightweight metadata for session start."""
        return {"name": self.name, "description": self.description}


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split YAML frontmatter from markdown body. Returns (yaml_str, body)."""
    text = text.strip()
    if not text.startswith("---"):
        return "", text

    rest = text[3:]
    idx = rest.find("\n---")
    if idx < 0:
        return "", text

    fm = rest[:idx].strip()
    body = rest[idx + 4 :].strip()
    return fm, body


def parse(path: str | Path) -> Skill:
    """Parse a SKILL.md file into a Skill object."""
    path = Path(path)
    return parse_text(path.read_text(encoding="utf-8"), str(path))


def parse_text(text: str, path: str = "<string>") -> Skill:
    """Parse SKILL.md content from a string."""
    fm_str, body = split_frontmatter(text)

    if not fm_str:
        raise ValueError(f"skill {path}: no YAML frontmatter found")

    data: dict[str, Any] = yaml.safe_load(fm_str) or {}

    description = data.get("description", "")
    if not description:
        raise ValueError(f"skill {path}: missing required field 'description'")

    name = data.get("name", "")
    if not name:
        name = Path(path).parent.name

    raw_meta = data.get("metadata", {}) or {}
    metadata = Metadata(
        persona=raw_meta.get("persona", ""),
        model=raw_meta.get("model", ""),
        temperature=(float(raw_meta["temperature"]) if "temperature" in raw_meta else None),
        max_tokens=int(raw_meta.get("max_tokens", 0)),
        max_iterations=int(raw_meta.get("max_iterations", 0)),
        tools=raw_meta.get("tools", []) or [],
        delegates=raw_meta.get("delegates", []) or [],
        allowed_tools=raw_meta.get("allowed_tools", []) or [],
        routing_signals=raw_meta.get("routing_signals", []) or [],
        boost_signals=raw_meta.get("boost_signals", []) or [],
    )

    # compatibility is parsed and stored for future environment-aware filtering
    # but not currently consumed by any routing or discovery logic.
    # See: docs/configuration-reference.md § Compatibility Field
    raw_compat = data.get("compatibility", [])
    compatibility = raw_compat if isinstance(raw_compat, list) else []

    return Skill(
        name=name,
        description=description,
        body=body,
        path=path,
        license=data.get("license", ""),
        compatibility=compatibility,
        metadata=metadata,
    )


def discover(directory: str | Path) -> list[Skill]:
    """Walk a skills directory and return all valid skills found."""
    d = Path(directory)
    if not d.is_dir():
        return []

    skills = []
    for entry in sorted(d.iterdir()):
        if not entry.is_dir():
            continue
        skill_path = entry / "SKILL.md"
        if not skill_path.exists():
            continue
        try:
            skills.append(parse(skill_path))
        except (ValueError, yaml.YAMLError) as e:
            _log.warning("skipping %s: %s", skill_path, e)
    return skills


def discover_map(directory: str | Path) -> dict[str, Skill]:
    """Like discover() but returns a dict keyed by skill name."""
    return {s.name: s for s in discover(directory)}


def catalog(directory: str | Path) -> list[dict[str, str]]:
    """Tier-1 progressive disclosure: return lightweight catalog entries.

    Each entry contains only name + description (~50-100 tokens per skill),
    keeping base context small while letting the agent know what's available.
    """
    return [s.catalog_entry for s in discover(directory)]


def _signal_matches(signal: str, text: str) -> bool:
    """Check if a routing signal appears in text with appropriate boundaries.

    Uses lookarounds instead of \\b to handle signals starting with
    non-word characters (e.g., ".py", ".go") where \\b would fail.
    """
    escaped = re.escape(signal)
    left = r"(?<![a-zA-Z0-9_])" if not signal[0].isalnum() else r"\b"
    right = r"(?![a-zA-Z0-9_])" if not signal[-1].isalnum() else r"\b"
    return bool(re.search(left + escaped + right, text))


def classify_agents(
    task: str,
    skills: dict[str, Skill],
    *,
    min_confidence: float = 0.0,
    top_n: int = 3,
) -> list[tuple[str, int]]:
    """Score agents by matching their routing_signals against a task description.

    Uses boundary matching to prevent false positives (e.g., "test"
    won't match "latest" or "contest"). Supports signals starting with
    non-word characters like ".py" or ".go" via lookaround boundaries.
    Returns a sorted list of (agent_name, score) with score > 0, highest first,
    limited to *top_n* results.

    When *min_confidence* > 0, agents scoring below the threshold are excluded.
    Default of 0.0 preserves backward compatibility (any match is returned).

    Disambiguation:
    - Demeter (orchestrator) is removed when specialists match.
    - Co-occurrence boosts resolve signal overlap (e.g., "pipeline").
    """
    task_lower = task.lower()
    scored: list[tuple[str, int]] = []

    for name, skill in skills.items():
        signals = skill.routing_signals
        if not signals:
            signals = [
                w.strip(".,;:()")
                for w in skill.description.lower().split()
                if len(w.strip(".,;:()")) > 3
            ]

        score = sum(1 for s in signals if _signal_matches(s.lower(), task_lower))
        if score > 0:
            scored.append((name, score))

    non_demeter = [(n, s) for n, s in scored if n != "demeter"]
    if non_demeter:
        scored = non_demeter

    # Co-occurrence boosts: if an agent already matched a routing signal
    # and any of its boost_signals appear in the task, add +2.
    # Boost signals are defined in each skill's SKILL.md metadata.
    for i, (name, score) in enumerate(scored):
        skill = skills.get(name)
        if (
            skill
            and skill.metadata.boost_signals
            and any(w in task_lower for w in skill.metadata.boost_signals)
        ):
            scored[i] = (name, score + 2)

    scored.sort(key=lambda x: x[1], reverse=True)
    if min_confidence > 0:
        scored = [(n, s) for n, s in scored if s >= min_confidence]
    return scored[:top_n]
