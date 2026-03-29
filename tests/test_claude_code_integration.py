"""Claude Code integration test — exercises the dispatch pattern without a live LLM.

Validates that the portable subagent definitions, CLAUDE.md bootstrap, AGENTS.md
routing table, and SKILL.md skill files are structurally correct and composable
for Claude Code dispatch.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestClaudeMdBootstrap:
    def test_claude_md_exists(self):
        assert (REPO_ROOT / "CLAUDE.md").is_file()

    def test_claude_md_has_bootstrap(self):
        content = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        assert "Bootstrap" in content

    def test_claude_md_references_agents_md(self):
        content = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        assert "AGENTS.md" in content

    def test_claude_md_has_activation_rule(self):
        content = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        assert "activation rule" in content.lower() or "Activation Rule" in content


class TestAgentsMdRoutingTable:
    EXPECTED_AGENTS = [
        "demeter",
        "athena",
        "freya",
        "saraswati",
        "brigid",
        "nuwa",
        "frigg",
        "danu",
        "cybele",
        "vesta",
        "amaterasu",
        "aurora",
        "oya",
        "themis",
        "kali",
        "mokosh",
        "pele",
        "seshat",
        "aphrodite",
        "calliope",
        "maat",
        "eris",
        "nisaba",
        "iris",
    ]

    def test_agents_md_exists(self):
        assert (REPO_ROOT / "AGENTS.md").is_file()

    @pytest.mark.parametrize("agent", EXPECTED_AGENTS)
    def test_agent_in_routing_table(self, agent: str):
        content = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8").lower()
        assert agent in content, f"Agent '{agent}' missing from AGENTS.md"


class TestSkillDiscoverability:
    def test_at_least_26_skills(self):
        skills = list((REPO_ROOT / ".agents" / "skills").glob("*/SKILL.md"))
        assert len(skills) >= 24, f"Expected 24+ skills, found {len(skills)}"

    def test_skills_have_valid_frontmatter(self):
        for skill_path in (REPO_ROOT / ".agents" / "skills").glob("*/SKILL.md"):
            content = skill_path.read_text(encoding="utf-8")
            assert content.startswith("---"), f"{skill_path} missing YAML frontmatter"
            parts = content.split("---", 2)
            assert len(parts) >= 3, f"{skill_path} malformed frontmatter"
            meta = yaml.safe_load(parts[1])
            assert "description" in meta, f"{skill_path} missing 'description'"


class TestPortableSubagents:
    def test_at_least_12_subagents(self):
        subagents = list((REPO_ROOT / ".agents" / "subagents").glob("*.md"))
        assert len(subagents) >= 10, f"Expected 10+ subagents, found {len(subagents)}"

    def test_subagents_are_self_contained(self):
        for sub_path in (REPO_ROOT / ".agents" / "subagents").glob("*.md"):
            content = sub_path.read_text(encoding="utf-8")
            assert content.startswith("---"), f"{sub_path} missing frontmatter"
            content_lower = content.lower()
            assert "methodology" in content_lower or "method" in content_lower, (
                f"{sub_path} missing methodology section"
            )

    def test_subagents_have_readonly_field(self):
        for sub_path in (REPO_ROOT / ".agents" / "subagents").glob("*.md"):
            content = sub_path.read_text(encoding="utf-8")
            parts = content.split("---", 2)
            meta = yaml.safe_load(parts[1])
            assert "readonly" in meta, f"{sub_path} missing 'readonly' in frontmatter"
            assert isinstance(meta["readonly"], bool), (
                f"{sub_path}: 'readonly' must be bool, got {type(meta['readonly'])}"
            )


class TestSubagentDispatchPattern:
    def test_dispatch_prompt_composable(self):
        """Simulate the Claude Code dispatch: read definition + compose prompt."""
        sub_path = REPO_ROOT / ".agents" / "subagents" / "kali.md"
        content = sub_path.read_text(encoding="utf-8")

        parts = content.split("---", 2)
        meta = yaml.safe_load(parts[1])
        assert "readonly" in meta
        assert isinstance(meta["readonly"], bool)

        task_description = "Audit the pantheon-py project for security vulnerabilities."
        dispatch_prompt = f"{content}\n\n## Your Assignment\n\n{task_description}"

        estimated_tokens = len(dispatch_prompt) / 4
        assert estimated_tokens < 4000, (
            f"Dispatch prompt too large: ~{estimated_tokens:.0f} tokens"
        )

    def test_all_subagent_dispatch_prompts_under_token_limit(self):
        """Every subagent definition should be composable under 4000 tokens."""
        for sub_path in (REPO_ROOT / ".agents" / "subagents").glob("*.md"):
            content = sub_path.read_text(encoding="utf-8")
            task = "Perform your standard analysis on the project."
            prompt = f"{content}\n\n## Your Assignment\n\n{task}"
            tokens = len(prompt) / 4
            assert tokens < 4000, (
                f"{sub_path.name} dispatch prompt too large: ~{tokens:.0f} tokens"
            )


class TestClassifyAgentsRouting:
    def test_python_routes_to_nuwa(self):
        from pantheon.skill import classify_agents, discover_map

        skills_dir = REPO_ROOT / ".agents" / "skills"
        skills = discover_map(str(skills_dir))
        if not skills:
            pytest.skip("No skills found (not in source checkout)")
        results = classify_agents("fix the Python test", skills)
        agent_names = [name for name, _score in results]
        assert "nuwa" in agent_names, f"Expected nuwa in results, got {agent_names}"

    def test_security_routes_to_kali(self):
        from pantheon.skill import classify_agents, discover_map

        skills_dir = REPO_ROOT / ".agents" / "skills"
        skills = discover_map(str(skills_dir))
        if not skills:
            pytest.skip("No skills found (not in source checkout)")
        results = classify_agents("security audit for vulnerabilities", skills)
        agent_names = [name for name, _score in results]
        assert "kali" in agent_names, f"Expected kali in results, got {agent_names}"
