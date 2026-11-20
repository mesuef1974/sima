"""حارس إيقاف القاعدة: عملية بلا نافذة ظاهرة توقف عنقود سِمة بنظافة حين يُنهي ويندوز الجلسة (إيقاف أو إعادة تشغيل أو خروج).

postgres خارج الخدمات لا يعالج إشارة الخروج من الجلسة (CTRL_LOGOFF_EVENT) فيُقطع، ويبدأ كل إقلاع باستعادة (pg.log:
«was not properly shut down»). الحارس يُبلَّغ قبل غيره (`SetProcessShutdownParameters` بأعلى مستوى للتطبيقات) فيرسل
إلى postmaster طلب الإيقاف السريع عبر أنبوب إشاراته `pgsignal_<pid>` (ما يفعله pg_ctl نفسه) بلا عملية جديدة، لأن إنشاء
العمليات يفشل والجلسة تنتهي (0xC0000142). إن أُلغي الإيقاف أعاد تشغيل القاعدة. يبدؤه `registry.cluster("start")`،
وواحد فقط لكل عنقود، ويخرج حين تتوقف القاعدة بغيره. `SIMA_DB_GUARD=0` يوقفه. السجل في `var/db_guard.log`.
"""
from __future__ import annotations

import hashlib
import sys
import time
from datetime import datetime
from pathlib import Path

SIGINT = 2  # الإيقاف السريع في postgres
WAIT_S = 4.0  # مهلة ويندوز لردّ التطبيق على انتهاء الجلسة خمس ثوانٍ
POLL_MS = 5000


def postmaster_pid(pgdata: Path) -> int | None:
    """رقم عملية postmaster من أول سطر في `postmaster.pid`؛ الغياب أو العطب يعني قاعدة متوقفة."""
    try:
        return int((pgdata / "postmaster.pid").read_text(encoding="ascii", errors="replace").splitlines()[0])
    except (OSError, ValueError, IndexError):
        return None


def signal_postmaster(pid: int, sig: int = SIGINT) -> bool:
    """يرسل إشارة إلى postgres على ويندوز كما يرسلها pg_ctl: بايت واحد في الأنبوب المسمّى للعملية."""
    import ctypes
    from ctypes import wintypes

    call = ctypes.WinDLL("kernel32", use_last_error=True).CallNamedPipeW
    call.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                     ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    call.restype = wintypes.BOOL
    data, ret, got = ctypes.c_ubyte(sig), ctypes.c_ubyte(0), wintypes.DWORD(0)
    return bool(call(f"\\\\.\\pipe\\pgsignal_{pid}", ctypes.byref(data), 1, ctypes.byref(ret), 1, ctypes.byref(got), 1000))


def fast_stop(pgdata: Path, send=signal_postmaster, wait_s: float = WAIT_S, sleep=time.sleep, clock=time.monotonic) -> str:
    """إيقاف سريع ينتظر زوال `postmaster.pid` (يُحذف حين يتمّ الإغلاق النظيف). يعيد: stopped | absent | refused | timeout."""
    pid = postmaster_pid(pgdata)
    if pid is None:
        return "absent"
    if not send(pid):
        return "refused"
    end = clock() + wait_s
    while clock() < end:
        if postmaster_pid(pgdata) is None:
            return "stopped"
        sleep(0.05)
    return "timeout"


def mutex_name(pgdata: Path) -> str:
    return "Local\\sima-db-guard-" + hashlib.sha256(str(pgdata.resolve()).lower().encode("utf-8")).hexdigest()[:16]


class Guard:
    """منطق الحارس بلا ويندوز: ما يفعله عند كل رسالة. `restart` يعيد تشغيل القاعدة إن أُلغي الإيقاف."""

    def __init__(self, pgdata: Path, log, stop=fast_stop, restart=None):
        self.pgdata, self.log, self.stop, self.restart = pgdata, log, stop, restart
        self.stopped_by_us = False

    def on_query_end(self) -> None:
        if self.stopped_by_us:
            return
        got = self.stop(self.pgdata)
        self.stopped_by_us = got == "stopped"
        self.log(f"انتهاء الجلسة: إيقاف القاعدة {got}")

    def on_end(self, ending: bool) -> None:
        if ending:
            self.on_query_end()  # لم يصل الاستعلام أو لم يكتمل: محاولة أخيرة
        elif self.stopped_by_us:
            self.stopped_by_us = False
            self.log("أُلغي الإيقاف: إعادة تشغيل القاعدة " + (self.restart() if self.restart else "غير متاحة"))

    def idle_done(self) -> bool:
        """القاعدة توقفت بغير الحارس (sima db stop): لا شيء يُحرس."""
        return not self.stopped_by_us and postmaster_pid(self.pgdata) is None


def _message_loop(guard: Guard) -> None:  # pragma: no cover — ويندوز وحده؛ يُختبر حيًّا
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
    WM_DESTROY, WM_QUERYENDSESSION, WM_ENDSESSION, WM_TIMER = 0x0002, 0x0011, 0x0016, 0x0113
    lresult = ctypes.c_ssize_t
    wndproc_t = ctypes.WINFUNCTYPE(lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", wndproc_t), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HANDLE), ("hCursor", wintypes.HANDLE),
                    ("hbrBackground", wintypes.HANDLE), ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = lresult
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HANDLE, wintypes.HINSTANCE, ctypes.c_void_p]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.ShutdownBlockReasonCreate.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user32.ShutdownBlockReasonDestroy.argtypes = [wintypes.HWND]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

    def proc(hwnd, msg, wparam, lparam):
        if msg == WM_QUERYENDSESSION:
            user32.ShutdownBlockReasonCreate(hwnd, "سِمة توقف قاعدتها بنظافة")
            guard.on_query_end()
            user32.ShutdownBlockReasonDestroy(hwnd)
            return 1
        if msg == WM_ENDSESSION:
            guard.on_end(bool(wparam))
            return 0
        if msg == WM_TIMER and guard.idle_done():
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    keep = wndproc_t(proc)  # يبقى حيًّا ما بقيت النافذة
    inst = kernel32.GetModuleHandleW(None)
    cls = WNDCLASSW(lpfnWndProc=keep, hInstance=inst, lpszClassName="SimaDbGuard")
    if not user32.RegisterClassW(ctypes.byref(cls)):
        raise ctypes.WinError(ctypes.get_last_error())
    # نافذة عليا لا تُعرض أبدًا: رسائل انتهاء الجلسة لا تصل النوافذ الرسائلية (HWND_MESSAGE)
    hwnd = user32.CreateWindowExW(0, "SimaDbGuard", "Sima DB Guard", 0, 0, 0, 0, 0, None, None, inst, None)
    if not hwnd:
        raise ctypes.WinError(ctypes.get_last_error())
    kernel32.SetProcessShutdownParameters(0x3FF, 0)  # أول من يُبلَّغ: قبل أن تصل postgres إشارة الخروج
    user32.SetTimer(hwnd, 1, POLL_MS, None)
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.DispatchMessageW(ctypes.byref(msg))


def main() -> int:  # pragma: no cover — ويندوز وحده
    import ctypes

    from .. import config
    from . import registry

    pgdata = registry.data_dir()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    held = kernel32.CreateMutexW(None, 0, mutex_name(pgdata))
    if not held or ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS: حارس آخر يعمل
        return 0
    path = config.ROOT / "var" / "db_guard.log"

    def log(line: str) -> None:
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")
        except OSError:
            pass

    if postmaster_pid(pgdata) is None:
        return 0
    log(f"بدأ الحارس (postmaster {postmaster_pid(pgdata)})")
    _message_loop(Guard(pgdata, log, restart=lambda: registry.cluster("start")[1]))
    log("خرج الحارس")
    return 0


if __name__ == "__main__":
    sys.exit(main())
