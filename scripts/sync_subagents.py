#!/usr/bin/env python3
"""Sync portable subagent definitions to Cursor format.

Reads .agents/subagents/*.md and writes .cursor/agents/*.md with
Cursor-specific additions (MCP server references, tool names).
The portable definitions in .agents/subagents/ are the single source of truth.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PORTABLE_DIR = REPO_ROOT / ".agents" / "subagents"
CURSOR_DIR = REPO_ROOT / ".cursor" / "agents"

CURSOR_ADDITIONS: dict[str, str] = {}


def _strip_compatibility(content: str) -> str:
    """Remove the compatibility: field from YAML frontmatter."""
    return re.sub(
        r"^compatibility:\s*\n(?:\s+-\s+.*\n)*",
        "",
        content,
        count=1,
        flags=re.MULTILINE,
    )


def sync() -> None:
    CURSOR_DIR.mkdir(parents=True, exist_ok=True)
    portable_files = sorted(PORTABLE_DIR.glob("*.md"))

    if not portable_files:
        print("No portable definitions found in", PORTABLE_DIR, file=sys.stderr)
        sys.exit(1)

    for src in portable_files:
        name = src.stem
        content = src.read_text(encoding="utf-8")

        content = _strip_compatibility(content)

        if name in CURSOR_ADDITIONS:
            insertion = CURSOR_ADDITIONS[name]
            for marker in ("## Output Contract", "## Constraints", "---"):
                if marker in content.split("---", 2)[-1]:
                    idx = content.rfind(marker) if marker == "---" else content.find(marker)
                    if idx > 0:
                        content = content[:idx] + insertion + content[idx:]
                        break

        dst = CURSOR_DIR / f"{name}.md"
        dst.write_text(content, encoding="utf-8")
        print(f"  {src.name} -> {dst.name}")

    print(f"\nSynced {len(portable_files)} definitions")


if __name__ == "__main__":
    sync()
