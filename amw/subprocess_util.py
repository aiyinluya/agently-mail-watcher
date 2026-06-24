from __future__ import annotations

import subprocess
import sys


def hidden_window_kwargs() -> dict:
    """Subprocess kwargs to avoid flashing console windows on Windows."""
    if sys.platform != "win32":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": flags, "startupinfo": startupinfo}


def resolve_pythonw() -> str:
    """Prefer pythonw.exe for background daemons on Windows."""
    exe = sys.executable
    if sys.platform == "win32":
        pyw = exe.replace("python.exe", "pythonw.exe")
        if pyw != exe:
            return pyw
    return exe
