#!/usr/bin/env python3
"""Login to local Cursor Agent CLI (not cloud Automation)."""

from __future__ import annotations

import subprocess
import sys

from amw.agent_cli import resolve_agent_cli


def main() -> int:
    cmd = resolve_agent_cli()
    if cmd == ["agent"] and not __import__("shutil").which("agent"):
        print("未找到 agent CLI。请先安装:", file=sys.stderr)
        if sys.platform == "win32":
            print("  irm 'https://cursor.com/install?win32=true' | iex", file=sys.stderr)
        else:
            print("  curl https://cursor.com/install -fsS | bash", file=sys.stderr)
        return 1

    print("正在启动 Cursor Agent 登录（浏览器授权）…")
    print("命令:", " ".join(cmd + ["login"]))
    return subprocess.call(cmd + ["login"])


if __name__ == "__main__":
    raise SystemExit(main())
