from __future__ import annotations

import json
import os
import re
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_path(base_dir: Path, maybe_relative: str | None) -> Path | None:
    if not maybe_relative:
        return None
    p = Path(maybe_relative)
    return p if p.is_absolute() else base_dir / p


def render_template(template: str, vars: dict[str, str]) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: vars.get(m.group(1), ""), template)


def log_line(log_dir: Path, name: str, line: str, *, echo: bool = False) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = log_dir / f"{name}-{day}.log"
    ts = utc_now_iso()
    msg = f"[{ts}] {line}\n"
    with log_file.open("a", encoding="utf-8") as f:
        f.write(msg)
    if echo:
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            print(msg, end="")
        except OSError:
            pass


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_lock(lock_file: Path, label: str) -> None:
    if lock_file.is_file():
        try:
            pid = int(lock_file.read_text(encoding="utf-8").strip())
            if pid_alive(pid):
                raise RuntimeError(f"{label} already running (pid {pid})")
        except ValueError:
            pass
    lock_file.write_text(str(os.getpid()), encoding="utf-8")


def release_lock(lock_file: Path) -> None:
    if not lock_file.is_file():
        return
    try:
        pid = int(lock_file.read_text(encoding="utf-8").strip())
        if pid == os.getpid():
            lock_file.unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


def install_signal_handlers(lock_file: Path) -> None:
    def _shutdown(signum: int, frame: object) -> None:
        release_lock(lock_file)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)
