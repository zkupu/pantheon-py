"""Tests for the SKILL.md parser."""

import logging
from pathlib import Path

import pytest

from pantheon.skill import (
    Metadata,
    Skill,
    catalog,
    classify_agents,
    discover,
    discover_map,
    parse_text,
    split_frontmatter,
)


class TestSplitFrontmatter:
    def test_standard(self):
        fm, body = split_frontmatter("---\nname: test\n---\n\n# Body")
        assert fm == "name: test"
        assert body == "# Body"

    def test_no_frontmatter(self):
        fm, body = split_frontmatter("# Just markdown\n\nContent")
        assert fm == ""
        assert body == "# Just markdown\n\nContent"

    def test_empty_body(self):
        fm, body = split_frontmatter("---\nname: test\n---\n")
        assert fm == "name: test"
        assert body == ""

    def test_whitespace_handling(self):
        fm, body = split_frontmatter("---\nname: test\n---\n\n  # Body  \n")
        assert fm == "name: test"
        assert body == "# Body"


class TestParseText:
    def test_full_skill(self):
        text = """---
name: athena
description: A strategist skill
license: MIT
metadata:
  persona: Your Devoted Strategist
  model: opus-4
  temperature: 0.5
  max_tokens: 8192
  tools:
    - read_file
    - list_dir
  delegates:
    - kali
---

# Athena

Body content."""

        s = parse_text(text, "/skills/athena/SKILL.md")
        assert s.name == "athena"
        assert s.description == "A strategist skill"
        assert s.license == "MIT"
        assert s.persona == "Your Devoted Strategist"
        assert s.model == "opus-4"
        assert s.temperature == 0.5
        assert s.max_tokens == 8192
        assert s.tool_names == ["read_file", "list_dir"]
        assert s.delegate_names == ["kali"]
        assert "# Athena" in s.body

    def test_missing_description_raises(self):
        with pytest.raises(ValueError, match="missing required field"):
            parse_text("---\nname: test\n---\n\nBody", "/test/SKILL.md")

    def test_name_inferred_from_path(self):
        text = "---\ndescription: inferred\n---\n\nBody"
        s = parse_text(text, "/skills/myskill/SKILL.md")
        assert s.name == "myskill"

    def test_no_frontmatter_raises(self):
        with pytest.raises(ValueError, match="no YAML frontmatter"):
            parse_text("# Just markdown", "/test.md")

    def test_defaults(self):
        s = parse_text("---\nname: x\ndescription: x\n---\n\nBody", "/x/SKILL.md")
        assert s.model == "meta/llama-3.3-70b-instruct"
        assert s.temperature == 0.7
        assert s.max_tokens == 4096
        assert s.max_iterations == 10
        assert s.tool_names == []
        assert s.delegate_names == []

    def test_metadata_without_tools(self):
        text = """---
name: eris
description: A challenger
metadata:
  model: nano
  temperature: 0.9
---

# Eris"""
        s = parse_text(text, "/skills/eris/SKILL.md")
        assert s.model == "nano"
        assert s.temperature == 0.9
        assert s.tool_names == []

    def test_routing_signals_parsed(self):
        text = """---
name: kali
description: Security protector
metadata:
  model: opus-4
  routing_signals:
    - security
    - vulnerability
    - threat model
---

# Kali"""
        s = parse_text(text, "/skills/kali/SKILL.md")
        assert s.routing_signals == ["security", "vulnerability", "threat model"]

    def test_routing_signals_default_empty(self):
        s = parse_text("---\nname: x\ndescription: x\n---\n\nBody", "/x/SKILL.md")
        assert s.routing_signals == []

    def test_boost_signals_parsed(self):
        text = """---
name: mokosh
description: CI/CD pipeline weaver
metadata:
  model: opus-4
  routing_signals:
    - pipeline
    - ci/cd
  boost_signals:
    - authoring
    - yaml
    - create
---

# Mokosh"""
        s = parse_text(text, "/skills/mokosh/SKILL.md")
        assert s.metadata.boost_signals == ["authoring", "yaml", "create"]

    def test_boost_signals_default_empty(self):
        s = parse_text("---\nname: x\ndescription: x\n---\n\nBody", "/x/SKILL.md")
        assert s.metadata.boost_signals == []


def _write_skill_md(directory: Path, name: str, description: str) -> None:
    """Create a minimal valid SKILL.md inside ``directory/name/``."""
    skill_dir = directory / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


class TestDiscoverResilience:
    def test_discover_with_valid_skills(self, tmp_path: Path) -> None:
        for name in ("alpha", "beta", "gamma"):
            _write_skill_md(tmp_path, name, f"{name} skill description")
        result = discover(tmp_path)
        assert len(result) == 3
        assert {s.name for s in result} == {"alpha", "beta", "gamma"}

    def test_discover_skips_malformed_yaml(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _write_skill_md(tmp_path, "good", "A valid skill")
        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        (bad_dir / "SKILL.md").write_text("---\n{{broken yaml!\n---\n\n# Bad\n", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="pantheon.skill"):
            result = discover(tmp_path)
        assert len(result) == 1
        assert result[0].name == "good"
        assert any("skipping" in r.message.lower() for r in caplog.records)

    def test_discover_skips_missing_description(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _write_skill_md(tmp_path, "good", "A valid skill")
        nodesc_dir = tmp_path / "nodesc"
        nodesc_dir.mkdir()
        (nodesc_dir / "SKILL.md").write_text(
            "---\nname: nodesc\n---\n\n# No desc\n", encoding="utf-8"
        )
        with caplog.at_level(logging.WARNING, logger="pantheon.skill"):
            result = discover(tmp_path)
        assert len(result) == 1
        assert result[0].name == "good"
        assert any("skipping" in r.message.lower() for r in caplog.records)

    def test_discover_empty_directory(self, tmp_path: Path) -> None:
        assert discover(tmp_path) == []

    def test_discover_nonexistent_directory(self, tmp_path: Path) -> None:
        assert discover(tmp_path / "does_not_exist") == []

    def test_discover_map_keys_are_skill_names(self, tmp_path: Path) -> None:
        for name in ("alpha", "beta"):
            _write_skill_md(tmp_path, name, f"{name} skill")
        result = discover_map(tmp_path)
        assert isinstance(result, dict)
        assert set(result.keys()) == {"alpha", "beta"}
        assert all(isinstance(v, Skill) for v in result.values())

    def test_catalog_returns_minimal_representation(self, tmp_path: Path) -> None:
        _write_skill_md(tmp_path, "alpha", "Alpha skill description")
        result = catalog(tmp_path)
        assert len(result) == 1
        entry = result[0]
        assert set(entry.keys()) == {"name", "description"}
        assert entry["name"] == "alpha"
        assert entry["description"] == "Alpha skill description"


def _make_skill(name: str, signals: list[str]) -> Skill:
    return Skill(
        name=name,
        description=f"{name} skill",
        body="",
        path=f"/skills/{name}/SKILL.md",
        metadata=Metadata(routing_signals=signals),
    )


class TestClassifyAgents:
    def test_demeter_removed_when_specialists_match(self):
        skills = {
            "demeter": _make_skill("demeter", ["general task", "direct action"]),
            "kali": _make_skill("kali", ["security", "vulnerability"]),
        }
        result = classify_agents("review security vulnerabilities", skills)
        names = [name for name, _ in result]
        assert "kali" in names
        assert "demeter" not in names

    def test_demeter_kept_when_only_match(self):
        skills = {
            "demeter": _make_skill("demeter", ["general task", "direct action"]),
            "kali": _make_skill("kali", ["security", "vulnerability"]),
        }
        result = classify_agents("handle this general task", skills)
        names = [name for name, _ in result]
        assert "demeter" in names

    def test_pipeline_authoring_routes_mokosh(self):
        skills = {
            "mokosh": _make_skill(
                "mokosh",
                [
                    "pipeline authoring",
                    "pipeline YAML",
                    "CI/CD pipeline",
                ],
            ),
            "kali": _make_skill("kali", ["security", "vulnerability"]),
        }
        result = classify_agents("write a CI/CD pipeline for this project", skills)
        assert result[0][0] == "mokosh"

    def test_co_occurrence_boost_mokosh(self):
        mokosh = _make_skill("mokosh", ["pipeline"])
        mokosh.metadata.boost_signals = ["authoring", "yaml", "write", "create", "ci/cd"]
        skills = {
            "mokosh": mokosh,
            "kali": _make_skill("kali", ["security"]),
        }
        result = classify_agents("create a new pipeline YAML for deployment", skills)
        mokosh_score = next((s for n, s in result if n == "mokosh"), 0)
        # Base signal "pipeline" scores 1, boost adds 2
        assert mokosh_score == 3

    def test_custom_boost_signals_from_metadata(self):
        """Boost signals defined in metadata increase score when co-occurring."""
        agent = _make_skill("seshat", ["data analysis", "sql"])
        agent.metadata.boost_signals = ["dashboard", "metrics", "report"]
        skills = {
            "seshat": agent,
            "kali": _make_skill("kali", ["security"]),
        }
        # "sql" matches routing signal (score 1), "dashboard" matches boost (+2)
        result = classify_agents("write sql to build a dashboard", skills)
        seshat_score = next((s for n, s in result if n == "seshat"), 0)
        assert seshat_score == 3

    def test_boost_signals_no_effect_without_routing_match(self):
        """Boost signals don't fire if no routing signal matched first."""
        agent = _make_skill("mokosh", ["pipeline"])
        agent.metadata.boost_signals = ["yaml", "create"]
        skills = {"mokosh": agent}
        # "create" matches boost but "pipeline" not in task -> no routing match -> no boost
        result = classify_agents("create a new yaml config file", skills)
        assert result == []

    def test_no_matches_returns_empty(self):
        skills = {
            "kali": _make_skill("kali", ["security", "vulnerability"]),
        }
        result = classify_agents("fix a typo in the readme", skills)
        assert result == []


class TestClassifyConfidence:
    def test_low_confidence_returns_empty_with_threshold(self) -> None:
        skills = {
            "kali": _make_skill("kali", ["security", "vulnerability"]),
            "themis": _make_skill("themis", ["testing", "coverage"]),
        }
        result = classify_agents(
            "fix a typo in the docs about security",
            skills,
            min_confidence=5.0,
        )
        assert result == []

    def test_clear_match_exceeds_threshold(self) -> None:
        skills = {
            "kali": _make_skill(
                "kali",
                [
                    "security",
                    "vulnerability",
                    "threat",
                    "attack",
                ],
            ),
        }
        result = classify_agents(
            "review security vulnerability and threat model for attack surface",
            skills,
            min_confidence=3.0,
        )
        assert len(result) >= 1
        assert result[0][0] == "kali"
        assert result[0][1] >= 3

    def test_backward_compatible_default(self) -> None:
        skills = {
            "kali": _make_skill("kali", ["security"]),
        }
        result = classify_agents("review security", skills)
        assert len(result) >= 1
        assert result[0][0] == "kali"
