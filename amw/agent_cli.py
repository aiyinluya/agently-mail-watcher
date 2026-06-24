from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any


def _cursor_agent_bases() -> list[Path]:
    bases: list[Path] = []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            bases.append(Path(local) / "cursor-agent")
    else:
        bases.extend(
            [
                Path.home() / ".local" / "share" / "cursor-agent",
                Path.home() / "Library" / "Application Support" / "cursor-agent",
            ]
        )
    return bases


def _resolve_from_versions() -> list[str] | None:
    node_name = "node.exe" if sys.platform == "win32" else "node"
    for base in _cursor_agent_bases():
        versions = base / "versions"
        if not versions.is_dir():
            continue
        entries = sorted(
            (p for p in versions.iterdir() if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
        for entry in entries:
            node = entry / node_name
            index = entry / "index.js"
            if node.is_file() and index.is_file():
                return [str(node), str(index)]
    return None


def resolve_agent_cli(config: dict[str, Any] | None = None) -> list[str]:
    """
    Resolve Cursor Agent CLI argv prefix.

    On Windows, avoid agent.cmd / agent.ps1 — their version-dir regex breaks on
    folders like 2026.06.19-20-24-33-653a7fb. Call bundled node.exe + index.js.
    """
    if config:
        la = config.get("localAgent") or {}
        if la.get("command"):
            return [la["command"]]

    direct = _resolve_from_versions()
    if direct:
        return direct

    if sys.platform != "win32":
        found = shutil.which("agent")
        if found:
            return [found]

    for base in _cursor_agent_bases():
        for name in ("agent.cmd", "agent"):
            candidate = base / name
            if candidate.is_file():
                return [str(candidate)]

    found = shutil.which("agent")
    return [found] if found else ["agent"]
