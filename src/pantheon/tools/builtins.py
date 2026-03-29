"""Concrete tool implementations: ShellExec, ReadFile, WriteFile, ListDir, SearchFiles."""

from __future__ import annotations

import logging
import os
import platform
import re as _re
import subprocess
from pathlib import Path

from .base import Registry, Tool, param, strict_schema
from .shell_safety import _check_allow_list, _check_deny_list

_log = logging.getLogger(__name__)
_MAX_READ_SIZE = 10 * 1024 * 1024

_SENSITIVE_FILE_RE = _re.compile(
    r"(?:^|\s)(?:cat|type|head|tail|less|more|bat|grep|rg|awk|sed)"
    r"\s+.*\.env(?!\.example|\.sample)\b"
)


def _is_sensitive_file(name: str) -> bool:
    """Match .env and variants (.env.local, .env.production, etc.) but not .env.example."""
    return name.startswith(".env") and name not in {".env.example", ".env.sample"}


def _check_allowed(path: Path, allowed_roots: list[Path] | None) -> str | None:
    """Return an error string if path is outside all allowed roots, or None if ok."""
    if not allowed_roots:
        return None
    resolved = path.resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root.resolve())
            return None
        except ValueError:
            continue
    roots_str = ", ".join(str(r) for r in allowed_roots)
    return f"error: path '{path}' is outside allowed roots: {roots_str}"


class ShellExec(Tool):
    def __init__(self, allowed_roots: list[str | Path] | None = None) -> None:
        self._allowed_roots = [Path(r) for r in allowed_roots] if allowed_roots else None

    def name(self) -> str:
        return "shell_exec"

    def description(self) -> str:
        return (
            "Execute a shell command in the system shell"
            " and return combined stdout/stderr output."
            " Use this tool to run build commands, install"
            " packages, query system state, or perform any"
            " operation available via the command line."
            " Destructive commands (rm -rf /, mkfs, piping"
            " downloads to shell) are blocked by policy."
            " The command times out after SHELL_EXEC_TIMEOUT"
            " seconds (default 60); long-running processes"
            " will be killed."
            " On Windows runs via cmd.exe; on Unix uses"
            " the user's default shell."
            " Returns '(no output)' when the command"
            " succeeds but produces no output."
        )

    def parameters(self) -> dict:
        return strict_schema(
            {
                "command": param(
                    "The shell command to execute, e.g. 'pip install requests' or 'ls -la'",
                ),
                "workdir": param(
                    "Working directory for the command. Pass empty string for current directory",
                ),
            },
            ["command", "workdir"],
        )

    def execute(self, args: dict) -> str:
        cmd = args["command"]
        if _SENSITIVE_FILE_RE.search(cmd):
            _log.warning("shell_exec secrets-file blocked: %s", cmd[:120])
            return "error: command accesses a secrets file (.env) — blocked by safety policy"
        mode = os.environ.get("SHELL_EXEC_MODE", "allow-list")
        if mode == "allow-list":
            if err := _check_allow_list(cmd):
                _log.warning("shell_exec allow-list blocked: %s", cmd[:120])
                return err
        if err := _check_deny_list(cmd):
            _log.warning("shell_exec blocked: %s", cmd[:120])
            return err
        cwd = args.get("workdir") or None
        if cwd is not None:
            if err := _check_allowed(Path(cwd), self._allowed_roots):
                return err

        if platform.system() == "Windows":
            shell_cmd = ["cmd.exe", "/c", cmd]
        else:
            shell = os.environ.get("SHELL", "/bin/sh")
            shell_cmd = [shell, "-c", cmd]

        _timeout = int(os.environ.get("SHELL_EXEC_TIMEOUT", "60"))
        try:
            result = subprocess.run(
                shell_cmd, capture_output=True, text=True, timeout=_timeout, cwd=cwd
            )
            output = (result.stdout + result.stderr).strip()
            if result.returncode != 0:
                return f"{output}\nexit code: {result.returncode}"
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return f"error: command timed out after {_timeout}s"


class ReadFile(Tool):
    def __init__(self, allowed_roots: list[str | Path] | None = None) -> None:
        self._allowed_roots = [Path(r) for r in allowed_roots] if allowed_roots else None

    def name(self) -> str:
        return "read_file"

    def description(self) -> str:
        return (
            "Read the full contents of a file and return"
            " it as a UTF-8 string. Use this tool when you"
            " need to inspect source code, configuration"
            " files, or any text file. Returns a descriptive"
            " error if the file does not exist or cannot be"
            " read. Does not support binary files; use"
            " shell_exec for binary operations."
        )

    def parameters(self) -> dict:
        return strict_schema(
            {
                "path": param(
                    "Absolute or relative file path to read, e.g. 'src/main.py'",
                ),
            },
            ["path"],
        )

    def execute(self, args: dict) -> str:
        try:
            p = Path(args["path"])
            if err := _check_allowed(p, self._allowed_roots):
                return err
            target_name = p.resolve().name if p.exists() else p.name
            if _is_sensitive_file(target_name):
                return f"error: reading '{target_name}' is blocked — secrets file"
            if p.stat().st_size > _MAX_READ_SIZE:
                return "error: file exceeds 10 MB limit"
            return p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return f"error: {e}"


class WriteFile(Tool):
    def __init__(self, allowed_roots: list[str | Path] | None = None) -> None:
        self._allowed_roots = [Path(r) for r in allowed_roots] if allowed_roots else None

    def name(self) -> str:
        return "write_file"

    def description(self) -> str:
        return (
            "Write text content to a file, creating any"
            " missing parent directories automatically."
            " Use this tool to create new files or overwrite"
            " existing ones with the provided content."
            " The file is written with UTF-8 encoding."
            " Returns a confirmation with the byte count"
            " written, or an error if the write fails."
        )

    def parameters(self) -> dict:
        return strict_schema(
            {
                "path": param(
                    "Absolute or relative file path to write, e.g. 'output/result.json'",
                ),
                "content": param(
                    "The full text content to write to the file",
                ),
            },
            ["path", "content"],
        )

    def execute(self, args: dict) -> str:
        try:
            p = Path(args["path"])
            if err := _check_allowed(p, self._allowed_roots):
                return err
            target_name = p.resolve().name if p.exists() else p.name
            if _is_sensitive_file(target_name):
                return f"error: writing '{target_name}' is blocked — secrets file"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], encoding="utf-8")
            return f"wrote {len(args['content'])} bytes to {p}"
        except OSError as e:
            return f"error: {e}"


class ListDir(Tool):
    def __init__(self, allowed_roots: list[str | Path] | None = None) -> None:
        self._allowed_roots = [Path(r) for r in allowed_roots] if allowed_roots else None

    def name(self) -> str:
        return "list_dir"

    def description(self) -> str:
        return (
            "List all files and subdirectories in a"
            " directory, one entry per line. Directory"
            " entries are suffixed with '/' to distinguish"
            " them from files. Use this tool to explore"
            " project structure or verify that expected"
            " files exist. Returns an error if the path"
            " does not exist or is not a directory."
        )

    def parameters(self) -> dict:
        return strict_schema(
            {
                "path": param(
                    "Absolute or relative path to the directory to list, e.g. 'src/'",
                ),
            },
            ["path"],
        )

    def execute(self, args: dict) -> str:
        try:
            p = Path(args["path"])
            if err := _check_allowed(p, self._allowed_roots):
                return err
            entries = sorted(p.iterdir())
            return "\n".join(f"{e.name}/" if e.is_dir() else e.name for e in entries)
        except OSError as e:
            return f"error: {e}"


class SearchFiles(Tool):
    def __init__(self, allowed_roots: list[str | Path] | None = None) -> None:
        self._allowed_roots = [Path(r) for r in allowed_roots] if allowed_roots else None

    def name(self) -> str:
        return "search_files"

    def description(self) -> str:
        return (
            "Recursively search for files matching a glob"
            " pattern, starting from a root directory."
            " Returns matching file paths (one per line),"
            " capped at 100 results. Supports Python glob"
            " syntax including '**/' for recursive matching."
            " Returns 'no matches found' if nothing matches."
        )

    def parameters(self) -> dict:
        return strict_schema(
            {
                "pattern": param(
                    "Glob pattern for matching files, e.g. '**/*.py', '*.test.js'",
                ),
                "root": param(
                    "Root directory to search from. Pass empty string for current directory",
                ),
            },
            ["pattern", "root"],
        )

    def execute(self, args: dict) -> str:
        root = Path(args.get("root", "."))
        if err := _check_allowed(root, self._allowed_roots):
            return err
        if ".." in Path(args["pattern"]).parts:
            return "error: pattern may not contain '..'"
        matches: list[Path] = []
        for match in root.glob(args["pattern"]):
            if _check_allowed(match, self._allowed_roots) is None:
                matches.append(match)
            if len(matches) >= 100:
                break
        return "\n".join(str(m) for m in matches) if matches else "no matches found"


def builtins(allowed_roots: list[str | Path] | None = None) -> Registry:
    """Create a registry with all built-in tools.

    When *allowed_roots* is provided, file and directory tools are restricted
    to those paths.  Defaults to ``[Path.cwd()]`` when *None* — callers that
    genuinely need unrestricted access must pass an empty list explicitly.
    """
    roots = allowed_roots if allowed_roots is not None else [Path.cwd()]
    r = Registry()
    for t in (
        ShellExec(allowed_roots=roots),
        ReadFile(allowed_roots=roots),
        WriteFile(allowed_roots=roots),
        ListDir(allowed_roots=roots),
        SearchFiles(allowed_roots=roots),
    ):
        r.register(t)
    return r
