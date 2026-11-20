"""قفل تشغيل لكل مشروع على القرص: `out/<مشروع>/.run.lock` فيه رقم العملية ووقت البدء.

يمنع تشغيلين متوازيين على المشروع نفسه، سواء من المنصة أو من الطرفية، ويبقى صحيحًا بعد إعادة تشغيل المنصة لأنه على القرص
لا في الذاكرة. القفل الذي ماتت عمليته يُستولى عليه. فحص حياة العملية على ويندوز بـ OpenProcess (لا os.kill الذي يُنهيها هناك).
والقفل يحمل وقت إنشاء عمليته: رقم عملية أعاد النظام استعماله لعملية أخرى ليس صاحب القفل (كان يحجب المشروع ويُظهره «يعمل»
حتى مهلة التشغيل، م4).
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

BUSY = 75  # رمز خروج sima run حين يكون المشروع مقفلًا بتشغيل آخر (EX_TEMPFAIL). كان 5 فصادم AWAIT_DESIGNER، فظلّت المنصة
# تعيد تشغيل الخط كل خمس ثوانٍ وهو ينتظر المصمّم الخارجي (اكتُشف 2026-11-13)


class ProjectBusy(RuntimeError):
    pass


def alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def created(pid: int) -> int | None:
    """وقت إنشاء العملية (FILETIME) على ويندوز؛ None إن تعذّرت قراءته أو على نظام آخر، وعندها يُكتفى برقم العملية."""
    if pid <= 0 or sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    born, gone, kernel, user = (wintypes.FILETIME() for _ in range(4))
    ok = k32.GetProcessTimes(h, ctypes.byref(born), ctypes.byref(gone), ctypes.byref(kernel), ctypes.byref(user))
    k32.CloseHandle(h)
    return (born.dwHighDateTime << 32) | born.dwLowDateTime if ok else None


def lock_path(out_dir: Path, project: str) -> Path:
    return out_dir / project / ".run.lock"


def holder(out_dir: Path, project: str) -> dict | None:
    """صاحب القفل إن كان حيًا، وإلا None."""
    p = lock_path(out_dir, project)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pid = int(data.get("pid", 0))
    if not alive(pid):
        return None
    born = data.get("created")  # قفل أقدم من الحقل: رقم العملية وحده
    if born is not None and created(pid) not in (None, born):
        return None  # الرقم نفسه لعملية وُلدت في وقت آخر: صاحب القفل مات وأُعيد استعمال رقمه
    return data


@contextlib.contextmanager
def project_lock(out_dir: Path, project: str) -> Iterator[None]:
    p = lock_path(out_dir, project)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = json.dumps({"pid": os.getpid(), "started": datetime.now(UTC).isoformat(timespec="seconds"),
                      "created": created(os.getpid())})
    for _ in range(2):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            h = holder(out_dir, project)
            if h:
                raise ProjectBusy(f"تشغيل آخر جارٍ على المشروع {project} (العملية {h['pid']} منذ {h.get('started', '')}).") from None
            p.unlink(missing_ok=True)  # قفل يتيم من عملية ماتت
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(rec)
        break
    else:
        raise ProjectBusy(f"تعذّر أخذ قفل المشروع {project}.")
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            if json.loads(p.read_text(encoding="utf-8")).get("pid") == os.getpid():
                p.unlink()
