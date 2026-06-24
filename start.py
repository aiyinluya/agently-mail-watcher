#!/usr/bin/env python3
"""Start watcher + processor daemons (cross-platform)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from amw.subprocess_util import hidden_window_kwargs, resolve_pythonw

ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Start Agently Mail Watcher services")
    p.add_argument(
        "--install-cron-hint",
        action="store_true",
        help="print suggested cron / launchd entries instead of starting",
    )
    return p.parse_args()


def ensure_config() -> None:
    cfg = ROOT / "config.json"
    example = ROOT / "config.example.json"
    if not cfg.is_file() and example.is_file():
        shutil.copy(example, cfg)
        print("已创建 config.json — 请编辑 watchFrom / replyTo。")


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def start_daemon(name: str, script: str, pid_file: Path, log_dir: Path) -> None:
    if pid_file.is_file():
        try:
            old = int(pid_file.read_text(encoding="utf-8").strip())
            if pid_alive(old):
                print(f"{name} already running (PID {old}).")
                return
        except ValueError:
            pass

    log_dir.mkdir(parents=True, exist_ok=True)
    out_log = log_dir / f"{script.replace('.py', '')}-stdout.log"
    err_log = log_dir / f"{script.replace('.py', '')}-stderr.log"
    out_f = out_log.open("a", encoding="utf-8")
    err_f = err_log.open("a", encoding="utf-8")

    kwargs: dict = {
        "cwd": ROOT,
        "stdout": out_f,
        "stderr": err_f,
        **hidden_window_kwargs(),
    }
    if sys.platform != "win32":
        kwargs["start_new_session"] = True

    py = resolve_pythonw()
    subprocess.Popen([py, script], **kwargs)
    time.sleep(2)

    if pid_file.is_file():
        print(f"{name} started (PID {pid_file.read_text(encoding='utf-8').strip()}).")
    else:
        print(f"{name} started; check {err_log} if PID file missing.")


def print_cron_hint() -> None:
  py = sys.executable
  root = ROOT
  print("Linux/macOS cron 示例（每分钟轮询一次，替代常驻 watcher）：")
  print(f"* * * * * cd {root} && {py} watcher.py --once >> logs/cron-watcher.log 2>&1")
  print(f"* * * * * cd {root} && {py} processor.py --once >> logs/cron-processor.log 2>&1")
  print()
  print("Windows 可用「任务计划程序」在登录时运行:")
  print(f"  {py} {root / 'start.py'}")


def main() -> int:
    args = parse_args()
    if args.install_cron_hint:
        print_cron_hint()
        return 0

    ensure_config()
    log_dir = ROOT / "logs"
    start_daemon("Mail watcher", "watcher.py", ROOT / "watcher.pid", log_dir)
    start_daemon("Local agent processor", "processor.py", ROOT / "processor.pid", log_dir)
    print(f"Logs: {log_dir}")
    print("首次使用请运行: python agent_login.py")
    print("邮箱授权: agently-cli auth login")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
