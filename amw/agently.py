from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from amw.subprocess_util import hidden_window_kwargs


class AgentlyError(Exception):
    pass


def _parse_cli_json(stdout: str) -> dict[str, Any]:
    start = stdout.find("{")
    if start < 0:
        raise AgentlyError(f"agently-cli: no JSON in output:\n{stdout}")
    return json.loads(stdout[start:])


def _npm_agently_entry() -> list[str] | None:
    """Direct node + run.js — avoids cmd.exe / .cmd console flash on Windows."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    npm = Path(appdata) / "npm"
    run_js = npm / "node_modules" / "@tencent-qqmail" / "agently-cli" / "scripts" / "run.js"
    if not run_js.is_file():
        return None
    node = npm / "node.exe"
    if node.is_file():
        prog = str(node)
    else:
        prog = shutil.which("node") or "node"
    return [prog, str(run_js)]


def resolve_agently_cli(config: dict[str, Any] | None) -> list[str]:
    if config and config.get("agentlyCliPath"):
        custom = str(config["agentlyCliPath"])
        if sys.platform == "win32" and custom.lower().endswith((".cmd", ".bat")):
            entry = _npm_agently_entry()
            if entry:
                return entry
        return [custom]

    entry = _npm_agently_entry()
    if entry:
        return entry

    found = shutil.which("agently-cli")
    if found and not found.lower().endswith((".cmd", ".bat")):
        return [found]

    return ["agently-cli"]


def run_agently(args: list[str], config: dict[str, Any] | None = None) -> Any:
    cmd = resolve_agently_cli(config)
    full = cmd + args
    result = subprocess.run(
        full,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        **hidden_window_kwargs(),
    )
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode != 0 and "{" not in stdout:
        raise AgentlyError((stderr or stdout or f"exit {result.returncode}").strip())

    envelope = _parse_cli_json(stdout)
    if not envelope.get("ok"):
        err = envelope.get("error") or {}
        msg = err.get("message") or json.dumps(err, ensure_ascii=False)
        raise AgentlyError(msg)
    return envelope.get("data")


def search_messages(
    *,
    from_addr: str | None = None,
    is_unread: bool = False,
    limit: int = 20,
    config: dict[str, Any] | None = None,
) -> list[Any]:
    args = ["message", "+search", "--limit", str(limit)]
    if from_addr:
        args.extend(["--from", from_addr])
    if is_unread:
        args.append("--is-unread")
    data = run_agently(args, config)
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict):
            return inner.get("data") or []
        return inner or []
    return []


def read_message(message_id: str, config: dict[str, Any] | None = None) -> Any:
    return run_agently(["message", "+read", "--id", message_id], config)
