"""Shell command deny/allow-list safety enforcement."""

from __future__ import annotations

import os
import platform
import re as _re
from pathlib import Path

_SHELL_DENY_UNIX = [
    _re.compile(r"rm\s+-(r|R|rf|Rf|fr|fR)\s+/(\s|$)"),
    _re.compile(r"rm\s+-(r|R|rf|Rf|fr|fR)\s+/\*"),
    _re.compile(r"rm\s+--recursive\b"),
    _re.compile(r"rm\s+(-\w+\s+)*-\w*[rR]\w*(\s+-\w+)*\s+/"),
    _re.compile(r"mkfs\b"),
    _re.compile(r"dd\s+.*of=/dev/"),
    _re.compile(r":\(\)\s*\{"),
    _re.compile(r">\s*/dev/sd"),
    _re.compile(r"chmod\s+.*777\s+/(\s|$)"),
    _re.compile(r"curl\s+.*\|\s*(ba)?sh"),
    _re.compile(r"wget\s+.*\|\s*(ba)?sh"),
    _re.compile(
        r"python[23]?\s+-c\s+.*(?:shutil\.rmtree|os\.remove|os\.unlink|subprocess)",
        _re.IGNORECASE,
    ),
    _re.compile(r"perl\s+-e\s+.*(?:system|unlink|rmtree)", _re.IGNORECASE),
    _re.compile(r"ruby\s+-e\s+.*(?:FileUtils|system|`)", _re.IGNORECASE),
    _re.compile(r"node\s+-e\s+.*(?:child_process|fs\.rm|execSync)", _re.IGNORECASE),
    _re.compile(r"base64\s+.*\|\s*(ba)?sh"),
    _re.compile(r"echo\s+.*\|\s*base64\s+.*\|\s*(ba)?sh"),
    _re.compile(r"powershell\.exe\b", _re.IGNORECASE),
    _re.compile(r"cmd\.exe\b", _re.IGNORECASE),
]

_SHELL_DENY_WINDOWS = [
    _re.compile(r"rd\s+/s\s+/q\s+[A-Z]:\\", _re.IGNORECASE),
    _re.compile(r"rmdir\s+/s\s+/q\s+[A-Z]:\\", _re.IGNORECASE),
    _re.compile(r"del\s+/[fFsS].*[A-Z]:\\", _re.IGNORECASE),
    _re.compile(r"\bformat\s+[A-Z]:", _re.IGNORECASE),
    _re.compile(r"Remove-Item\s+.*-Recurse.*[A-Z]:\\", _re.IGNORECASE),
    _re.compile(r"Remove-Item\s+.*[A-Z]:\\.*-Recurse", _re.IGNORECASE),
    _re.compile(r"powershell\s+.*-enc", _re.IGNORECASE),
    _re.compile(r"powershell\s+.*-encodedcommand", _re.IGNORECASE),
    _re.compile(r"Invoke-WebRequest\s+.*\|\s*Invoke-Expression", _re.IGNORECASE),
    _re.compile(r"iwr\s+.*\|\s*iex", _re.IGNORECASE),
    _re.compile(r"python\s+-c\s+.*(?:shutil\.rmtree|os\.remove|subprocess)", _re.IGNORECASE),
    _re.compile(r"pwsh\b.*-enc", _re.IGNORECASE),
    _re.compile(r"wmic(\.exe)?\s+process\s+call\s+create", _re.IGNORECASE),
    _re.compile(r"mshta\b", _re.IGNORECASE),
    _re.compile(r"cscript\b", _re.IGNORECASE),
    _re.compile(r"wscript\b", _re.IGNORECASE),
    _re.compile(r"reg(\.exe)?\s+delete\b", _re.IGNORECASE),
    _re.compile(r"bcdedit\b", _re.IGNORECASE),
    _re.compile(r"wsl(\.exe)?\b", _re.IGNORECASE),
    _re.compile(r"certutil(\.exe)?\b.*-(urlcache|encode|decode|decodehex)", _re.IGNORECASE),
    _re.compile(r"rundll32(\.exe)?\b", _re.IGNORECASE),
    _re.compile(r"regsvr32(\.exe)?\b", _re.IGNORECASE),
    _re.compile(r"bitsadmin(\.exe)?\b.*/(transfer|create|addfile|resume)", _re.IGNORECASE),
]

_SHELL_DENY_COMMON: list[_re.Pattern[str]] = []

_SHELL_DENY_PATTERNS = (
    (_SHELL_DENY_COMMON + _SHELL_DENY_WINDOWS)
    if platform.system() == "Windows"
    else (_SHELL_DENY_COMMON + _SHELL_DENY_UNIX)
)


def _normalize_for_deny_check(cmd: str) -> str:
    """Strip common shell quoting that could bypass deny patterns."""
    return _re.sub(r"""[\"'\\]""", "", cmd)


def _check_deny_list(cmd: str) -> str | None:
    """Return an error string if the command matches a deny pattern."""
    normalized = _normalize_for_deny_check(cmd)
    for pattern in _SHELL_DENY_PATTERNS:
        if pattern.search(cmd) or pattern.search(normalized):
            return "error: command blocked by safety policy — matches deny pattern"
    return None


_DEFAULT_ALLOW_LIST = frozenset(
    {
        "git",
        # python/python3/node excluded — write-then-execute chain bypasses
        # all controls.  Add to SHELL_EXEC_ALLOW_LIST explicitly if needed.
        "pip",
        "pip3",
        "pytest",
        "ruff",
        "mypy",
        "black",
        "ls",
        "dir",
        "cat",
        "type",
        "head",
        "tail",
        "grep",
        "rg",
        "find",
        "fd",
        "mkdir",
        "cp",
        "mv",
        "touch",
        "echo",
        "printf",
        "wc",
        # docker intentionally excluded from default — volume mounts can
        # bypass all path confinement.  Operators who need it should add
        # docker,docker-compose to SHELL_EXEC_ALLOW_LIST explicitly.
        "make",
        "cmake",
        "go",
        "cargo",
        "npm",
        "dotnet",
        "msbuild",
    }
)


def _get_allow_list() -> frozenset[str]:
    """Resolve the active allow-list: user env var, or built-in default."""
    raw = os.environ.get("SHELL_EXEC_ALLOW_LIST")
    if raw is None:
        return _DEFAULT_ALLOW_LIST
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


_SHELL_CHAIN_PATTERN = _re.compile(r"[\n\r;|&`]|\$\(|>\s*>?|<\s*<?\(")

_INTERPRETER_CMDS = frozenset({"python", "python3", "python2", "node", "ruby", "perl"})
_INLINE_EXEC_RE = _re.compile(r"\s+-\w*[ceE]\b")

# npm exec / npx can run arbitrary code — block these even though npm
# itself (for install/ci) is on the allow-list.
_NPM_EXEC_RE = _re.compile(r"(?:^|\s)(?:npx|npm\s+exec)\b")


def _check_allow_list(cmd: str) -> str | None:
    """In allow-list mode, only pre-approved command base names are permitted."""
    allow_list = _get_allow_list()
    if not allow_list:
        return "error: SHELL_EXEC_ALLOW_LIST is empty — no commands allowed in allow-list mode"
    if _SHELL_CHAIN_PATTERN.search(cmd):
        return (
            "error: command contains shell metacharacters"
            " — chaining/piping/redirection not permitted in allow-list mode"
        )
    first_word = cmd.strip().split()[0] if cmd.strip() else ""
    base_cmd = first_word.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if base_cmd not in allow_list:
        return (
            f"error: command '{base_cmd}' not in allow-list"
            f" — permitted: {', '.join(sorted(allow_list))}"
        )
    if base_cmd in _INTERPRETER_CMDS and _INLINE_EXEC_RE.search(cmd):
        return (
            f"error: inline code execution via '{base_cmd} -c/-e'"
            " is not permitted"
            " — write code to a file and run the file instead"
        )
    if _NPM_EXEC_RE.search(cmd):
        return "error: 'npm exec' / 'npx' can run arbitrary code — blocked by safety policy"
    return None


# ---------------------------------------------------------------------------
# Path argument validation — Kali F-01
# ---------------------------------------------------------------------------

_FILE_READING_CMDS = frozenset(
    {"cat", "head", "tail", "grep", "rg", "find", "fd", "ls", "less", "more", "bat"}
)


def _check_path_arguments(cmd: str, allowed_roots: list[Path] | None) -> str | None:
    """Validate that path-like arguments stay within *allowed_roots*.

    Only applies to file-reading commands (cat, head, tail, grep, etc.).
    Returns an error string if a path escapes the sandbox, or *None* if ok.
    """
    if not allowed_roots:
        return None

    parts = cmd.strip().split()
    if not parts:
        return None

    base_cmd = parts[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if base_cmd not in _FILE_READING_CMDS:
        return None

    resolved_roots = [r.resolve() for r in allowed_roots]

    for arg in parts[1:]:
        # Skip flags
        if arg.startswith("-"):
            continue
        # Only check args that look like paths (contain / or start
        # with .).  Bare words are likely patterns (grep) not paths.
        if "/" not in arg and not arg.startswith("."):
            continue

        try:
            p = Path(arg).resolve()
        except (OSError, ValueError):
            continue

        inside = False
        for root in resolved_roots:
            try:
                p.relative_to(root)
                inside = True
                break
            except ValueError:
                continue

        if not inside:
            roots_str = ", ".join(str(r) for r in allowed_roots)
            return (
                f"error: path argument '{arg}' is outside allowed roots: {roots_str}"
                " — blocked by safety policy"
            )

    return None
