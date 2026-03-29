#!/usr/bin/env python3
"""Cross-platform installer for the Pantheon Cursor integration.

Creates the necessary links from ~/.cursor/ into the pantheon-py repository
so Cursor picks up skills, agents, and rules.

On Unix: creates symbolic links (default behavior).
On Windows: uses directory junctions for directories and file copies for
individual files, unless Developer Mode is enabled (detected automatically),
in which case native symlinks are used.

Usage:
    python scripts/install.py          # install links
    python scripts/install.py --check  # dry-run: show what would happen
    python scripts/install.py --clean  # remove installed links/copies
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
from pathlib import Path


def find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / ".agents" / "skills").is_dir():
            return candidate
    raise SystemExit("Could not locate the Pantheon repository root")


def cursor_home() -> Path:
    """Return the user-level .cursor directory."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("USERPROFILE", Path.home()))
    else:
        base = Path.home()
    return base / ".cursor"


def _windows_developer_mode() -> bool:
    """Check if Windows Developer Mode is enabled (allows unprivileged symlinks)."""
    if platform.system() != "Windows":
        return False
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock",
        )
        value, _ = winreg.QueryValueEx(key, "AllowDevelopmentWithoutDevLicense")
        winreg.CloseKey(key)
        return bool(value)
    except Exception:
        return False


def _windows_junction(source: Path, target: Path) -> None:
    """Create a directory junction on Windows via mklink /J."""
    subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(target), str(source)],
        check=True,
        capture_output=True,
    )


def _is_junction(path: Path) -> bool:
    """Check if a path is a Windows junction point."""
    if platform.system() != "Windows":
        return False
    try:
        import ctypes

        FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        return attrs != -1 and bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except Exception:
        return False


def _remove_link(path: Path, *, dry_run: bool = False) -> bool:
    """Remove a symlink, junction, or file. Returns True if something was removed."""
    if not path.exists() and not path.is_symlink():
        return False

    if dry_run:
        print(f"  would remove: {path}")
        return True

    if path.is_symlink():
        path.unlink()
    elif _is_junction(path):
        if platform.system() == "Windows":
            subprocess.run(
                ["cmd.exe", "/c", "rmdir", str(path)],
                check=True,
                capture_output=True,
            )
        else:
            path.rmdir()
    elif path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)

    return True


def _link_directory(source: Path, target: Path, *, use_symlinks: bool, dry_run: bool) -> str:
    """Link a directory: symlink, junction, or copy."""
    if dry_run:
        method = "symlink" if use_symlinks else "junction"
        return f"  {method}: {target} -> {source}"

    target.parent.mkdir(parents=True, exist_ok=True)
    _remove_link(target)

    if use_symlinks:
        target.symlink_to(source, target_is_directory=True)
    elif platform.system() == "Windows":
        _windows_junction(source, target)
    else:
        target.symlink_to(source, target_is_directory=True)

    method = "symlink" if use_symlinks else "junction"
    return f"  {method}: {target} -> {source}"


def _link_file(source: Path, target: Path, *, use_symlinks: bool, dry_run: bool) -> str:
    """Link a file: symlink or copy."""
    if dry_run:
        method = "symlink" if use_symlinks else "copy"
        return f"  {method}: {target} -> {source}"

    target.parent.mkdir(parents=True, exist_ok=True)
    _remove_link(target)

    if use_symlinks:
        target.symlink_to(source)
    else:
        shutil.copy2(source, target)

    method = "symlink" if use_symlinks else "copy"
    return f"  {method}: {target} -> {source}"


DIRECTORY_LINKS = [
    (".agents/skills", "skills"),
]

FILE_LINKS = [
    (".cursor/agents/aphrodite.md", "agents/aphrodite.md"),
    (".cursor/agents/athena.md", "agents/athena.md"),
    (".cursor/agents/eris.md", "agents/eris.md"),
    (".cursor/agents/iris.md", "agents/iris.md"),
    (".cursor/agents/kali.md", "agents/kali.md"),
    (".cursor/agents/themis.md", "agents/themis.md"),
]

RULE_LINKS = [
    (".cursor/rules/pantheon.mdc", "rules/pantheon.mdc"),
    (".cursor/rules/pantheon-voice.mdc", "rules/pantheon-voice.mdc"),
]


def install(repo: Path, cursor: Path, *, use_symlinks: bool, dry_run: bool) -> list[str]:
    actions: list[str] = []

    for repo_rel, cursor_rel in DIRECTORY_LINKS:
        source = repo / repo_rel
        target = cursor / cursor_rel
        if not source.is_dir():
            actions.append(f"  SKIP (source missing): {source}")
            continue
        actions.append(_link_directory(source, target, use_symlinks=use_symlinks, dry_run=dry_run))

    for repo_rel, cursor_rel in FILE_LINKS + RULE_LINKS:
        source = repo / repo_rel
        target = cursor / cursor_rel
        if not source.is_file():
            actions.append(f"  SKIP (source missing): {source}")
            continue
        actions.append(_link_file(source, target, use_symlinks=use_symlinks, dry_run=dry_run))

    return actions


def clean(cursor: Path, *, dry_run: bool) -> list[str]:
    actions: list[str] = []
    for _, cursor_rel in DIRECTORY_LINKS:
        target = cursor / cursor_rel
        if _remove_link(target, dry_run=dry_run):
            if not dry_run:
                actions.append(f"  removed: {target}")

    for _, cursor_rel in FILE_LINKS + RULE_LINKS:
        target = cursor / cursor_rel
        if _remove_link(target, dry_run=dry_run):
            if not dry_run:
                actions.append(f"  removed: {target}")

    return actions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install Pantheon skills, agents, and rules into Cursor",
    )
    parser.add_argument("--check", action="store_true", help="Dry-run: show what would happen")
    parser.add_argument("--clean", action="store_true", help="Remove installed links/copies")
    parser.add_argument(
        "--cursor-home",
        type=Path,
        default=None,
        help="Override ~/.cursor path (default: auto-detected)",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Force file copies instead of symlinks (default on Windows without Developer Mode)",
    )
    args = parser.parse_args(argv)

    repo = find_repo_root()
    cursor = args.cursor_home or cursor_home()

    is_windows = platform.system() == "Windows"
    use_symlinks = not is_windows or (_windows_developer_mode() and not args.copy)

    if args.copy:
        use_symlinks = False

    print(f"Repository: {repo}")
    print(f"Cursor home: {cursor}")
    print(f"Platform: {platform.system()}")
    print(f"Link method: {'symlinks' if use_symlinks else 'junctions + copies'}")
    print()

    if args.clean:
        print("Cleaning installed links...")
        actions = clean(cursor, dry_run=args.check)
        for a in actions:
            print(a)
        if not actions:
            print("  nothing to clean")
        return 0

    print("Installing Pantheon into Cursor...")
    actions = install(repo, cursor, use_symlinks=use_symlinks, dry_run=args.check)
    for a in actions:
        print(a)

    if args.check:
        print("\nDry run — no changes made.")
    else:
        print("\nInstallation complete.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
