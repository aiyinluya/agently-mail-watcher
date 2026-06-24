#!/usr/bin/env python3
"""Stop watcher + processor daemons (including orphaned processes)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from amw.subprocess_util import hidden_window_kwargs

ROOT = Path(__file__).resolve().parent


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def subprocess_kill(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            check=False,
            capture_output=True,
            **hidden_window_kwargs(),
        )
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def stop_by_pid_file(label: str, pid_file: Path) -> None:
    if not pid_file.is_file():
        print(f"No {label} pid file.")
        return
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        pid_file.unlink(missing_ok=True)
        print(f"Invalid {label} pid file removed.")
        return

    if pid_alive(pid):
        subprocess_kill(pid)
        print(f"Stopped {label} (PID {pid}).")
    else:
        print(f"Stale {label} PID ({pid}); removing pid file.")
    pid_file.unlink(missing_ok=True)


def _list_python_processes_win() -> list[tuple[int, str]]:
    """Enumerate python/pythonw processes via wmic (no PowerShell)."""
    out = subprocess.run(
        [
            "wmic",
            "process",
            "where",
            "name='python.exe' or name='pythonw.exe'",
            "get",
            "ProcessId,CommandLine",
            "/format:list",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        **hidden_window_kwargs(),
    )
    if out.returncode != 0:
        return []

    rows: list[tuple[int, str]] = []
    pid = 0
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("ProcessId="):
            try:
                pid = int(line.split("=", 1)[1] or 0)
            except ValueError:
                pid = 0
        elif line.startswith("CommandLine="):
            cmd = line.split("=", 1)[1]
            if pid > 0:
                rows.append((pid, cmd))
            pid = 0
    return rows


def stop_orphan_processes() -> None:
    """Kill watcher/processor/agent_login started from this tool but missing pid files."""
    if sys.platform != "win32":
        return
    root = str(ROOT).lower()
    markers = ("watcher.py", "processor.py", "agent_login.py")
    try:
        for pid, cmd in _list_python_processes_win():
            lowered = cmd.lower()
            if root not in lowered:
                continue
            if not any(m in lowered for m in markers):
                continue
            subprocess_kill(pid)
            print(f"Stopped orphan process (PID {pid}).")
    except Exception as exc:
        print(f"Orphan scan skipped: {exc}")


def main() -> int:
    stop_by_pid_file("processor", ROOT / "processor.pid")
    stop_by_pid_file("watcher", ROOT / "watcher.pid")
    stop_orphan_processes()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
