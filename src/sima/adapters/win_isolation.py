"""عزل استدعاء النموذج على مستوى النظام في ويندوز: عملية بمستوى سلامة منخفض (Low integrity) داخل Job.

الحصار في `claude_model.py` قواعد يطبّقها claude على أدواته؛ هذا الملف طبقة تحته يفرضها النظام نفسه على العملية وكل ما تتفرّع
عنه، ولو أخطأت القواعد أو تغيّر سلوكها:
- العملية المنخفضة لا تكتب في أي ملف أو مجلد وسمه متوسط (وهو الافتراضي لكل ملفات المستخدم)، فلا تكتب إلا في «نافذة الكتابة»
  التي توسَم منخفضة مدة الاستدعاء ثم تُردّ.
- ما وُسم «لا يُقرأ من أدنى» (الأسرار) لا تقرؤه. بقية ملفات الجهاز تبقى مقروءة للنظام، وحارسها قواعد claude.
- العملية وأحفادها في Job يُقتل كله عند المهلة أو عند موت الخط.

بـ ctypes وحده، بلا حزم. الوسوم تُوضع بـ SetFileSecurity على كل عنصر صراحةً (بلا اعتماد على توريث لاحق)، وما يُنشأ أثناء
الاستدعاء يرث وسم مجلده عند إنشائه.
"""
from __future__ import annotations

import contextlib
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator
from functools import cache
from pathlib import Path
from types import SimpleNamespace

LOW_DIR, LOW_FILE = "S:(ML;OICI;NW;;;LW)", "S:(ML;;NW;;;LW)"
MEDIUM_DIR, MEDIUM_FILE = "S:(ML;OICI;NW;;;ME)", "S:(ML;;NW;;;ME)"
SECRET_DIR, SECRET_FILE = "S:(ML;OICI;NWNR;;;ME)", "S:(ML;;NWNR;;;ME)"  # NR: لا يُقرأ من مستوى أدنى

_LOW_SID = "S-1-16-4096"
_TOKEN_ALL = 0xF01FF
_SECURITY_IMPERSONATION, _TOKEN_PRIMARY, _TOKEN_INTEGRITY_LEVEL = 2, 1, 25
_SE_GROUP_INTEGRITY = 0x20
_LABEL_INFO = 0x10  # LABEL_SECURITY_INFORMATION
_CREATE_SUSPENDED, _CREATE_UNICODE_ENVIRONMENT, _CREATE_NO_WINDOW = 0x4, 0x400, 0x08000000
_STARTF_USESTDHANDLES = 0x100
_JOB_EXTENDED_LIMIT, _JOB_KILL_ON_CLOSE = 9, 0x2000
_WAIT_OBJECT_0 = 0

_DWORD, _WORD, _HANDLE = ctypes.c_uint32, ctypes.c_uint16, ctypes.c_void_p


class _SidAndAttributes(ctypes.Structure):
    _fields_ = (("Sid", ctypes.c_void_p), ("Attributes", _DWORD))


class _StartupInfo(ctypes.Structure):
    _fields_ = (("cb", _DWORD), ("lpReserved", ctypes.c_wchar_p), ("lpDesktop", ctypes.c_wchar_p), ("lpTitle", ctypes.c_wchar_p),
                ("dwX", _DWORD), ("dwY", _DWORD), ("dwXSize", _DWORD), ("dwYSize", _DWORD), ("dwXCountChars", _DWORD),
                ("dwYCountChars", _DWORD), ("dwFillAttribute", _DWORD), ("dwFlags", _DWORD), ("wShowWindow", _WORD),
                ("cbReserved2", _WORD), ("lpReserved2", ctypes.c_void_p), ("hStdInput", _HANDLE), ("hStdOutput", _HANDLE),
                ("hStdError", _HANDLE))


class _ProcessInformation(ctypes.Structure):
    _fields_ = (("hProcess", _HANDLE), ("hThread", _HANDLE), ("dwProcessId", _DWORD), ("dwThreadId", _DWORD))


class _BasicLimit(ctypes.Structure):
    _fields_ = (("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", _DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", _DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", _DWORD), ("SchedulingClass", _DWORD))


class _IoCounters(ctypes.Structure):
    _fields_ = tuple((n, ctypes.c_uint64) for n in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes"))


class _ExtendedLimit(ctypes.Structure):
    _fields_ = (("BasicLimitInformation", _BasicLimit), ("IoInfo", _IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t))


def available() -> bool:
    return sys.platform == "win32"


@cache
def _win() -> SimpleNamespace:
    """دوال Win32 بتواقيعها؛ تُحمَّل عند أول استعمال فيبقى الملف مستوردًا على غير ويندوز."""
    adv, k32 = ctypes.WinDLL("advapi32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
    p, wstr, ptr = ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER
    sigs = {
        (k32, "GetCurrentProcess"): ((), _HANDLE), (k32, "CloseHandle"): ((_HANDLE,), ctypes.c_int),
        (k32, "WaitForSingleObject"): ((_HANDLE, _DWORD), _DWORD), (k32, "GetExitCodeProcess"): ((_HANDLE, ptr(_DWORD)), ctypes.c_int),
        (k32, "CreateJobObjectW"): ((p, wstr), _HANDLE), (k32, "SetInformationJobObject"): ((_HANDLE, ctypes.c_int, p, _DWORD), ctypes.c_int),
        (k32, "AssignProcessToJobObject"): ((_HANDLE, _HANDLE), ctypes.c_int), (k32, "TerminateJobObject"): ((_HANDLE, _DWORD), ctypes.c_int),
        (k32, "ResumeThread"): ((_HANDLE,), _DWORD), (k32, "LocalFree"): ((p,), p),
        (adv, "OpenProcessToken"): ((_HANDLE, _DWORD, ptr(_HANDLE)), ctypes.c_int),
        (adv, "DuplicateTokenEx"): ((_HANDLE, _DWORD, p, ctypes.c_int, ctypes.c_int, ptr(_HANDLE)), ctypes.c_int),
        (adv, "ConvertStringSidToSidW"): ((wstr, ptr(p)), ctypes.c_int), (adv, "GetLengthSid"): ((p,), _DWORD),
        (adv, "SetTokenInformation"): ((_HANDLE, ctypes.c_int, p, _DWORD), ctypes.c_int),
        (adv, "CreateProcessAsUserW"): ((_HANDLE, wstr, p, p, p, ctypes.c_int, _DWORD, p, wstr, p, p), ctypes.c_int),
        (adv, "ConvertStringSecurityDescriptorToSecurityDescriptorW"): ((wstr, _DWORD, ptr(p), p), ctypes.c_int),
        (adv, "ConvertSecurityDescriptorToStringSecurityDescriptorW"): ((p, _DWORD, _DWORD, ptr(p), p), ctypes.c_int),
        (adv, "SetFileSecurityW"): ((wstr, _DWORD, p), ctypes.c_int), (adv, "GetFileSecurityW"): ((wstr, _DWORD, p, _DWORD, ptr(_DWORD)), ctypes.c_int),
    }
    for (lib, name), (args, res) in sigs.items():
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = args, res
    return SimpleNamespace(adv=adv, k32=k32)


def _check(ok: int, what: str) -> None:
    if not ok:
        code = ctypes.get_last_error()
        raise OSError(code, f"{what}: {ctypes.FormatError(code).strip()}")


# ---- الوسوم ----

def set_label(path: Path, sddl: str) -> None:
    a, sd = _win(), ctypes.c_void_p()
    _check(a.adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None), "وسم غير صالح")
    try:
        _check(a.adv.SetFileSecurityW(str(path), _LABEL_INFO, sd), f"تعذّر وسم {path}")
    finally:
        a.k32.LocalFree(sd)


def get_label(path: Path) -> str:
    """وسم السلامة بصيغة SDDL، أو نص فارغ إن لم يوسَم (فهو متوسط ضمنًا)."""
    a, need = _win(), _DWORD(0)
    a.adv.GetFileSecurityW(str(path), _LABEL_INFO, None, 0, ctypes.byref(need))
    if not need.value:
        return ""
    buf, text = ctypes.create_string_buffer(need.value), ctypes.c_void_p()
    _check(a.adv.GetFileSecurityW(str(path), _LABEL_INFO, buf, need, ctypes.byref(need)), f"تعذّرت قراءة وسم {path}")
    _check(a.adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(buf, 1, _LABEL_INFO, ctypes.byref(text), None), "تحويل الوسم")
    try:
        return ctypes.wstring_at(text.value) if text.value else ""
    finally:
        a.k32.LocalFree(text)


def _is_link(p: Path) -> bool:
    return p.is_symlink() or p.is_junction()  # الرابط لا يوسَم ولا يُتبع: هدفه قد يكون خارج الشجرة


def label_tree(root: Path, dir_sddl: str, file_sddl: str) -> None:
    """يوسم الجذر وكل ما تحته صراحةً."""
    if _is_link(root) or not root.exists():
        return
    if root.is_file():
        set_label(root, file_sddl)
        return
    set_label(root, dir_sddl)
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not _is_link(Path(base) / d)]
        for d in dirs:
            set_label(Path(base) / d, dir_sddl)
        for f in files:
            if not _is_link(Path(base) / f):
                set_label(Path(base) / f, file_sddl)


def protect(paths: Iterable[Path]) -> None:
    """يوسم الأسرار «لا تُقرأ من أدنى». ما وُسم سابقًا يُتجاوز، وما يُنشأ داخله لاحقًا يرث الوسم."""
    for p in paths:
        if p.exists() and not _is_link(p) and "NR" not in get_label(p):
            label_tree(p, SECRET_DIR, SECRET_FILE)


@contextlib.contextmanager
def write_window(scope: Path, target: Path, locked: Iterable[Path] = ()) -> Iterator[None]:
    """نافذة الكتابة لاستدعاء واحد: scope كله متوسط، ثم target منخفض، ثم locked (داخل target) متوسطة.
    تُردّ target إلى المتوسط في النهاية ولو فشل الاستدعاء، فلا يبقى في السكون مجلد يُكتب فيه من المنخفض."""
    label_tree(scope, MEDIUM_DIR, MEDIUM_FILE)
    label_tree(target, LOW_DIR, LOW_FILE)
    for p in locked:
        label_tree(p, MEDIUM_DIR, MEDIUM_FILE)
    try:
        yield
    finally:
        label_tree(target, MEDIUM_DIR, MEDIUM_FILE)


# ---- العملية ----

def _low_token(a: SimpleNamespace) -> ctypes.c_void_p:
    tok, new, sid = _HANDLE(), _HANDLE(), ctypes.c_void_p()
    _check(a.adv.OpenProcessToken(a.k32.GetCurrentProcess(), _TOKEN_ALL, ctypes.byref(tok)), "OpenProcessToken")
    try:
        _check(a.adv.DuplicateTokenEx(tok, _TOKEN_ALL, None, _SECURITY_IMPERSONATION, _TOKEN_PRIMARY, ctypes.byref(new)),
               "DuplicateTokenEx")
    finally:
        a.k32.CloseHandle(tok)
    _check(a.adv.ConvertStringSidToSidW(_LOW_SID, ctypes.byref(sid)), "ConvertStringSidToSid")
    try:
        label = _SidAndAttributes(sid, _SE_GROUP_INTEGRITY)
        size = ctypes.sizeof(label) + a.adv.GetLengthSid(sid)
        _check(a.adv.SetTokenInformation(new, _TOKEN_INTEGRITY_LEVEL, ctypes.byref(label), size), "SetTokenInformation")
    except OSError:
        a.k32.CloseHandle(new)
        raise
    finally:
        a.k32.LocalFree(sid)
    return new


def _job(a: SimpleNamespace) -> ctypes.c_void_p:
    job = a.k32.CreateJobObjectW(None, None)
    _check(job, "CreateJobObject")
    info = _ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = _JOB_KILL_ON_CLOSE  # إن مات الخط مات النموذج وأحفاده
    _check(a.k32.SetInformationJobObject(job, _JOB_EXTENDED_LIMIT, ctypes.byref(info), ctypes.sizeof(info)), "SetInformationJobObject")
    return _HANDLE(job)


def _env_block(env: dict[str, str]) -> ctypes.Array:
    pairs = sorted(env.items(), key=lambda kv: kv[0].upper())
    return ctypes.create_unicode_buffer("".join(f"{k}={v}\0" for k, v in pairs) + "\0")


def run_low(cmd: list[str], cwd: Path, timeout: float, env: dict[str, str] | None = None,
            tick: Callable[[], None] | None = None, every: float = 0.7) -> subprocess.CompletedProcess:
    """مثل proc.run_tree، والعملية بمستوى سلامة منخفض داخل Job. المهلة تقتل الـJob كله ثم ترفع TimeoutExpired."""
    import msvcrt

    a = _win()
    token, job = _low_token(a), _job(a)
    pi = _ProcessInformation()
    try:
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, open(os.devnull, "rb") as nul:
            # ملفات يفتحها الأب ويرثها الابن: المخرجات لا تحتاج مجلدًا يُكتب فيه من المنخفض
            handles = [msvcrt.get_osfhandle(f.fileno()) for f in (nul, out, err)]
            for h in handles:
                os.set_handle_inheritable(h, True)
            si = _StartupInfo()
            si.cb, si.dwFlags = ctypes.sizeof(si), _STARTF_USESTDHANDLES
            si.hStdInput, si.hStdOutput, si.hStdError = handles
            line = ctypes.create_unicode_buffer(subprocess.list2cmdline(cmd))
            block = _env_block(dict(os.environ) if env is None else env)
            flags = _CREATE_SUSPENDED | _CREATE_UNICODE_ENVIRONMENT | _CREATE_NO_WINDOW
            _check(a.adv.CreateProcessAsUserW(token, None, line, None, None, True, flags, block, str(cwd), ctypes.byref(si),
                                              ctypes.byref(pi)), "CreateProcessAsUser")
            in_job = bool(a.k32.AssignProcessToJobObject(job, pi.hProcess))

            def kill() -> None:
                if in_job:
                    a.k32.TerminateJobObject(job, 1)
                else:  # تعذّر ضمّه إلى الـJob: قتل الشجرة بالطريقة القديمة
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pi.dwProcessId)], capture_output=True,
                                   creationflags=_CREATE_NO_WINDOW, check=False)
                a.k32.WaitForSingleObject(pi.hProcess, 10_000)

            try:
                a.k32.ResumeThread(pi.hThread)
                deadline = time.monotonic() + timeout
                while a.k32.WaitForSingleObject(pi.hProcess, int(max(0.0, min(every, deadline - time.monotonic())) * 1000)) != _WAIT_OBJECT_0:
                    if time.monotonic() >= deadline:
                        kill()
                        raise subprocess.TimeoutExpired(cmd, timeout)
                    if tick is not None:
                        with contextlib.suppress(Exception):
                            tick()
            except BaseException:  # المهلة أو Ctrl+C أو خروج: لا يبقى النموذج يتيمًا ينفق ويكتب
                kill()
                raise
            code = _DWORD()
            a.k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
            out.seek(0)
            err.seek(0)
            return subprocess.CompletedProcess(cmd, ctypes.c_int32(code.value).value, out.read().decode("utf-8", "replace"),
                                               err.read().decode("utf-8", "replace"))
    finally:
        for h in (pi.hThread, pi.hProcess, job, token):
            if h:
                a.k32.CloseHandle(h)
