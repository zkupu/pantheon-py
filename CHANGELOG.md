# Changelog

## Unreleased

### Added
- 8 new agents: frigg (PowerShell), danu (C), cybele (C++), vesta (C#),
  amaterasu (DirectX), aurora (Vulkan), oya (NVIDIA GPU)
- Portable subagent definitions in `.agents/subagents/` for Claude Code
- `pantheon auto` command with `--lead` and `--dry-run` flags
- Claude Code bootstrap instructions in CLAUDE.md
- Claude Code + WSL 2 setup guide in README.md
- Compressed routing fallback in CLAUDE.md for instruction decay resistance
- WSL 2 cross-environment deny patterns (powershell.exe, cmd.exe, wsl.exe)
- `docs/cli-reference.md`, `docs/configuration-reference.md`, `docs/runtime-reference.md`
- `docs/research/instruction-decay.md` — field study on instruction decay
- `docs/workflows.md` — portable prompt templates for Cursor slash commands
- `pantheon doctor --claude-code` diagnostic subcommand
- `/rally` command for full specialist dispatch with visible classification

### Changed
- CLAUDE.md: added Bootstrap section, Quick Reference routing, subagent dispatch
  instructions, rally decision guide, re-anchor checkpoint
- AGENTS.md: expanded Claude Code dispatch instructions with Read+Task workflow
- Subagent dispatch threshold lowered from 7 turns to 5 turns in CLAUDE.md
- `.gitignore`: added `.coverage`, `.pytest_cache/`, `.ruff_cache/`
- All SKILL.md files annotated with `# Runtime-only` metadata comment
- Rate limiting environment variables documented in configuration reference

### Fixed
- Bundled the canonical skill set into published installs and added packaged-install smoke checks
- Enforced gateway request timeouts, restored interactive chat history correctly, and tightened orchestration deadline handling
- Made audit logging lazy, added redaction for sensitive tool inputs and outputs, and enforced `allowed_tools`
- Hardened the self-improvement pipeline so frontmatter must remain unchanged and model-generated rewrites require explicit apply opt-in
- Clarified documentation around privileged shell access, bundled skills, trusted `.env` usage, and optional `litellm` integration
- Made audit logging best-effort, blocked `search_files` results from escaping allowed roots, and validated file-store session IDs
- Enforced budget limits before tool execution/final replies, clarified best-effort orchestration deadlines
- Stale subagent count in freya SKILL.md

## 0.2.0 — Toolkit Expansion

### Added
- Cursor subagents, eval automation, improvement tooling, and expanded Pantheon skill coverage
- Inference API configuration and `INFERENCE_API_KEY` support across runtime and CI
- Project scripts for model access probing and benchmark reruns

## 0.1.0 — Initial Release

### Added
- Agent runtime with ReAct loop, streaming, and tool dispatch
- OpenAI-compatible gateway client with retry logic and SSE streaming
- Tool interface with Registry, strict schema validation, and built-in tools (shell, read, write, list, search)
- Multi-agent orchestration: Team (agent-as-tool), Pipeline (sequential), Review (fan-out + synthesize)
- SKILL.md parser following agentskills.io specification
- File-backed session persistence with window trimming and summary compression
- Structured tracing and cost estimation
- CLI with commands: list, chat, ask, run, team, pipe, review, warroom
- 16 specialist agent skills
- Optional path restrictions on file tools for sandboxed execution
