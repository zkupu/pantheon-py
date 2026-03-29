"""Tool interface, registry, and built-in tools."""

from .audit import (
    AuditLogger,
    _default_auditor,
    _get_last_hash,
    setup_audit_log,
    verify_audit_chain,
)
from .base import Registry, Tool, _validate_args, check_required, param, strict_schema
from .builtins import (
    ListDir,
    ReadFile,
    SearchFiles,
    ShellExec,
    WriteFile,
    builtins,
)
from .shell_safety import (
    _DEFAULT_ALLOW_LIST,
    _SHELL_DENY_UNIX,
    _SHELL_DENY_WINDOWS,
    _check_allow_list,
    _check_deny_list,
)

__all__ = [
    "AuditLogger",
    "ListDir",
    "ReadFile",
    "Registry",
    "SearchFiles",
    "ShellExec",
    "Tool",
    "WriteFile",
    "_DEFAULT_ALLOW_LIST",
    "_SHELL_DENY_UNIX",
    "_SHELL_DENY_WINDOWS",
    "_check_allow_list",
    "_check_deny_list",
    "_default_auditor",
    "_get_last_hash",
    "_validate_args",
    "builtins",
    "check_required",
    "param",
    "setup_audit_log",
    "strict_schema",
    "verify_audit_chain",
]
