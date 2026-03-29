"""Tests for the eval improvement helper script."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_improve_module():
    module_path = Path(__file__).resolve().parents[1] / "evals" / "bin" / "improve.py"
    spec = importlib.util.spec_from_file_location("pantheon_improve_script", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_skill_content_rejects_frontmatter_changes():
    improve = _load_improve_module()
    original = """---
name: athena
description: test skill
metadata:
  model: original-model
---

# Athena

This is a sufficiently long body that passes the size check.
"""
    rewritten = original.replace("original-model", "changed-model")

    result = improve._validate_skill_content(rewritten, original)
    assert result == "Frontmatter changed; only the Markdown body may be rewritten"


def test_validate_skill_content_allows_body_only_changes():
    improve = _load_improve_module()
    original = """---
name: athena
description: test skill
metadata:
  model: original-model
---

# Athena

This is a sufficiently long body that passes the size check.
"""
    rewritten = """---
name: athena
description: test skill
metadata:
  model: original-model
---

# Athena

This is a sufficiently long body that passes the size check, but now it
contains clearer verification guidance for the agent to follow.
"""

    assert improve._validate_skill_content(rewritten, original) is None
