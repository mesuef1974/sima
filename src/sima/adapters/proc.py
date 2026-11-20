"""تشغيل عملية فرعية بلا نافذة، وقتل شجرتها كاملة عند المهلة: لا يبقى claude ولا Chromium يتيمًا ينفق أو يكتب بعد المهلة.

على ويندوز: `taskkill /T /F` على رأس الشجرة (يشمل node خلف claude.cmd). وعلى غيره: مجموعة عمليات مستقلة تُقتل بـ killpg.
"""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, creationflags=NO_WINDOW, check=False)
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def run_tree(cmd: list[str], cwd: Path, timeout: float, env: dict[str, str] | None = None,
             tick: Callable[[], None] | None = None, every: float = 0.7) -> subprocess.CompletedProcess:
    """مثل subprocess.run مع التقاط المخرجات، لكن المهلة تقتل الشجرة كلها ثم ترفع TimeoutExpired.
    tick يُستدعى في الخيط نفسه كل `every` ثانية ما دامت العملية تعمل (عين الرسّام)؛ خطؤه لا يوقف العملية."""
    extra = {"creationflags": NO_WINDOW} if sys.platform == "win32" else {"start_new_session": True}
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                            encoding="utf-8", errors="replace", env=env, **extra)
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        try:
            out, err = proc.communicate(timeout=max(0.0, min(every, left) if tick else left))
            break
        except subprocess.TimeoutExpired:
            if tick is None or time.monotonic() >= deadline:
                kill_tree(proc)
                proc.communicate()
                raise subprocess.TimeoutExpired(cmd, timeout) from None
            with contextlib.suppress(Exception):
                tick()
        except BaseException:  # Ctrl+C أو خروج: لا يبقى claude يتيمًا ينفق ويكتب بعد توقف الخط
            kill_tree(proc)
            raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
