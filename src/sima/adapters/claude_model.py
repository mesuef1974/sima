"""محوّل النموذج: يستدعي Claude Code بلا نافذة (`claude -p`) لتنفيذ طلب واحد من طلبات الخط.

اتصال سحابي وافق عليه المالك صراحة (2026-11-09)، ومعطّل ما لم يكن SIMA_MODEL_AUTO=1 في .env. الحصار:
- القراءة فقط في المستودع، والكتابة محصورة في `work/` الإصدار نفسه؛ لا Bash ولا ويب.
- سقف كلفة لكل استدعاء (SIMA_MODEL_BUDGET_USD) ومهلة زمنية، ولا جلسة محفوظة.
- يُرسل الطلب ومراجعه المحلية فقط؛ لا أسرار (.env محجوب عن القراءة).
- وتحت هذه القواعد عزل يفرضه النظام على العملية نفسها (win_isolation.py): مستوى سلامة منخفض داخل Job.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from .. import config
from ..services.autopilot import ModelResult
from .proc import run_tree

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TOOLS = ("Read", "Glob", "Grep", "Write", "Edit")
DENY = ("Bash", "WebFetch", "WebSearch", "Read(./.env)", "Read(./.env.*)", "Read(./**/.env)", "Read(./**/.env.*)",
        "Read(./var/**)", "Read(./.git/**)", "Read(./vendor/**/.git/**)")
PROMPT = """أنت النموذج المصمم في خط سِمة. نفّذ الطلب في الملف {req} كاملًا وبدقة.
مجلد الإصدار: {root}. كل مسار يبدأ بـ work/ في الطلب نسبي إلى مجلد الإصدار، فاكتب فيه هناك فقط ({root}/work/).
اقرأ ما يحيل إليه الطلب من المستودع (.claude/skills/sima-design/SKILL.md وdocs/ وwork/research.md). لا تنسخ شيئًا من vendor/.
اكتب الملفات المطلوبة فقط بالصيغة المطلوبة، ثم انتهِ بجملة عربية واحدة تلخّص ما كتبت."""


def _env(key: str, default: str) -> str:
    return config.ENV.get(key, default)  # القارئ الوحيد للبيئة: .env ثم متغيرات البيئة، بلا إعدادات Django


def enabled() -> bool:
    return _env("SIMA_MODEL_AUTO", "0") == "1" and shutil.which("claude") is not None


BLIND_PROMPT = """أنت قارئ مستقل في خط سِمة: ترى صورًا ولا تعرف ما قُصد بها. نفّذ الطلب في الملف {req} بدقة.
مجلد الإصدار: {root}. اقرأ الصور المذكورة في الطلب وحدها، ولا تحاول قراءة أي ملف آخر.
اكتب الملف المطلوب فقط في {root}/work/blind/، ثم انتهِ بجملة عربية واحدة تلخّص ما كتبت."""

# REQUEST-fix تصحيح صيغة ملف كتبه الرسّام: نموذجه بالجهد المتوسط لا العالي (ليس في IDEA_REQUESTS)، فلا يُعاد الطلب الإبداعي كاملًا
DESIGN_REQUESTS = ("REQUEST-diverge", "REQUEST-critique", "REQUEST-refine", "REQUEST-judge", "REQUEST-style", "REQUEST-blind",
                   "REQUEST-thumbs", "REQUEST-fix")


IDEA_REQUESTS = ("REQUEST-diverge", "REQUEST-style", "REQUEST-thumbs")  # توليد الأفكار والرسم الأول: الجهد الأعلى هنا لا في الصقل الميكانيكي
DRAWER_MODEL, JUDGE_MODEL = "claude-fable-5-2", "opus"  # قرار المالك 2026-11-11: Fable يرسم وopus يحكم (حَكَم لا يستحسن أسلوب نفسه)
BLIND_MODEL = "sonnet"  # القارئ الأعمى نموذج ثالث غير الرسّام والحَكَم: يصف ما يراه فقط، فيكفيه جهد منخفض


def design_flags(request_name: str) -> list[str]:
    """الرسم والنقد والصقل بنموذج الرسّام، والتحكيم بنموذج مستقل؛ بقية الطلبات بالافتراضي. الجهد العالي للأفكار والرسم الأول
    (`SIMA_MODEL_EFFORT_IDEAS`)، والصقل والنقد بـ `SIMA_MODEL_EFFORT`: الصقل كان أكبر بنود كلفة v1 (20 من 57 دولارًا)."""
    if not request_name.startswith(DESIGN_REQUESTS):
        return []
    flags = []
    model, effort = _env("SIMA_MODEL_DESIGN", DRAWER_MODEL), _env("SIMA_MODEL_EFFORT", "medium")
    if request_name.startswith(IDEA_REQUESTS):
        effort = _env("SIMA_MODEL_EFFORT_IDEAS", "high")
    if request_name.startswith("REQUEST-judge"):
        model, effort = _env("SIMA_MODEL_JUDGE", JUDGE_MODEL), _env("SIMA_MODEL_JUDGE_EFFORT", effort)
    if request_name.startswith("REQUEST-blind"):
        model, effort = _env("SIMA_MODEL_BLIND", BLIND_MODEL), _env("SIMA_MODEL_BLIND_EFFORT", "low")
    if model:
        flags += ["--model", model]
    if effort:
        flags += ["--effort", effort]
    return flags


def settings() -> dict[str, str]:
    """ما يُستدعى به كل دور الآن؛ يُحفظ مع نتائج التقييم لتُنسب إلى إعدادها."""
    return {"design_model": _env("SIMA_MODEL_DESIGN", DRAWER_MODEL), "effort_ideas": _env("SIMA_MODEL_EFFORT_IDEAS", "high"),
            "effort": _env("SIMA_MODEL_EFFORT", "medium"), "judge_model": _env("SIMA_MODEL_JUDGE", JUDGE_MODEL),
            "blind_model": _env("SIMA_MODEL_BLIND", BLIND_MODEL), "isolation": isolation() or "none"}


def max_calls() -> int:
    return int(_env("SIMA_MODEL_MAX_CALLS", "16"))  # قرار المالك 2026-11-14: الدورة الأولى 9 إلى 13 استدعاءً، وسقف 10 كان يقفها في منتصفها


def max_total_usd() -> float:
    return float(_env("SIMA_MODEL_TOTAL_USD", "15"))  # قرار المالك 2026-11-14: الدورة الأولى تكلّف 10 إلى 12 دولارًا


def call_timeout_s() -> int:
    """مهلة الاستدعاء الواحد (45 دقيقة): رسم Fable بجهد عالٍ استغرق 22.6 دقيقة، ومهلة 25 كانت ستقطعه بعد أن أنفق."""
    return int(_env("SIMA_MODEL_TIMEOUT_S", "2700"))


# الحَكَم مستقل فعلًا: كتابته محصورة في work/judge/ فلا يستطيع تعديل ما يحكم عليه
# وعينات الطابع محصورة في work/styles/ فلا تمسّ المفاهيم
# والقارئ الأعمى أضيق: يكتب في work/blind/ ولا يقرأ إلا طلبه وصور التصيير، فلا يصل إلى الاسم ولا الفكرة ولا الموجز
CONFINED = {"REQUEST-judge": "judge", "REQUEST-style": "styles", "REQUEST-blind": "blind"}
GUARDED = ("judge", "blind")  # ما لا يكتبه الرسّام: حكم الحَكَم وقراءة القارئ
REPLY_MAX = 8000  # جواب النموذج كاملًا يُحفظ في سجل الاستدعاءات حتى هذا الحد (يُعرض على المالك حين يجيب طلب تعديل بلا تغيير)
TMP_DIR = "model-tmp"  # أبو المجلدات المؤقتة للعمليات المعزولة داخل var/ (خارج git): لكل استدعاء مجلده، يُحذف بعده


def confined_sub(request_name: str) -> str | None:
    return next((d for prefix, d in CONFINED.items() if request_name.startswith(prefix)), None)


def isolation() -> str:
    """عزل النظام للاستدعاء: «low» افتراضيًا على ويندوز (مستوى سلامة منخفض داخل Job، adapters/win_isolation.py).
    `SIMA_MODEL_ISOLATION=0` يوقفه. وإن تعذّر العزل وهو مفعّل فشل الاستدعاء ولا يُستدعى النموذج بلا عزل."""
    from . import win_isolation

    return "low" if win_isolation.available() and _env("SIMA_MODEL_ISOLATION", "low") == "low" else ""


def _digest(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for root in paths:
        files = [root] if root.is_file() else sorted(x for x in root.rglob("*") if x.is_file()) if root.is_dir() else []
        for f in files:
            h.update(f.as_posix().encode("utf-8") + bytes([0]) + f.read_bytes() + bytes([0]))
    return h.hexdigest()


class ClaudeCodeModel:
    def __init__(self, root: Path | None = None, budget_usd: float | None = None, timeout_s: int | None = None):
        self._root = root or config.ROOT
        self._budget = budget_usd if budget_usd is not None else float(_env("SIMA_MODEL_BUDGET_USD", "5"))
        self._timeout = timeout_s or call_timeout_s()

    def _locked(self, request: Path, version_root: Path) -> list[Path]:
        """ما لا يملكه النموذج داخل work/: طلباته كلها، وللرسّام حكم الحَكَم وقراءة القارئ. المجلدان يُنشآن إن غابا:
        كان القفل يتخطّى ما لم يوجد بعد، فيستطيع الرسّام في أول استدعاء أن يكتب حكمًا أو قراءة قبل صاحبيهما."""
        work = version_root / "work"
        locked = sorted(work.glob("REQUEST-*"))
        if confined_sub(request.name) is None:
            for d in GUARDED:
                (work / d).mkdir(parents=True, exist_ok=True)
            locked += [work / d for d in GUARDED]
        return locked

    def _secrets(self) -> list[Path]:
        """ما يوسَم «لا يُقرأ من أدنى»: ملفات .env و.git وكل ما في var/ عدا متصفح التصيير (عملياته منخفضة السلامة وتقرؤه)."""
        var = self._root / "var"
        keep = {config.BROWSERS_DIR.name, TMP_DIR}
        return [*self._root.glob(".env*"), self._root / ".git", *(p for p in (var.iterdir() if var.is_dir() else ()) if p.name not in keep)]

    def _spawn(self, cmd: list[str], request: Path, version_root: Path, tick: Callable[[], None] | None) -> subprocess.CompletedProcess:
        env = {**os.environ, "SIMA_MODEL_AUTO": "0"}  # لا استدعاء متداخل
        if not isolation():
            return run_tree(cmd, self._root, self._timeout, env=env, tick=tick)
        from . import win_isolation as wi

        work = version_root / "work"
        sub = confined_sub(request.name)
        target = work / sub if sub else work
        target.mkdir(parents=True, exist_ok=True)
        base = self._root / "var" / TMP_DIR
        base.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="call-", dir=base))  # لكل استدعاء مجلده: استدعاء مشروع آخر لا يحذف مؤقت هذا
        wi.protect(self._secrets())
        try:
            with wi.write_window(work, target, self._locked(request, version_root)), wi.write_window(tmp, tmp):
                return wi.run_low(cmd, self._root, self._timeout, env={**env, "TEMP": str(tmp), "TMP": str(tmp)}, tick=tick)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            with contextlib.suppress(OSError):
                base.rmdir()  # يزول الأب حين يفرغ؛ وإن بقي فيه مؤقت استدعاء آخر جارٍ بقي

    def command(self, request: Path, version_root: Path, budget_usd: float | None = None) -> list[str]:
        """الحصار طبقات: أدوات الملفات الخمس وحدها (لا Bash ولا ويب ولا وكلاء ولا MCP)، وبلا إعدادات المستخدم وخطافاته
        وأذوناته العامة، والقراءة محصورة في المستودع بقاعدة سماح وحيدة في وضع dontAsk (كل ما سواها مرفوض)، ثم حجب
        صريح للأسرار والعنقود وgit حتى داخل المستودع. يُثبت فعليًا بـ scripts/probe_confinement.py."""
        root = self._root.resolve()
        rel = version_root.resolve().relative_to(root).as_posix()
        sub = confined_sub(request.name)
        work =f"./{rel}/work/{sub}/**" if sub else f"./{rel}/work/**"
        req = request.resolve().relative_to(root).as_posix()
        blind = sub == "blind"
        reads = [f"Read(./{req})", f"Read(./{rel}/work/render/**)"] if blind else ["Read(./**)"]
        return [
            shutil.which("claude") or "claude", "-p", (BLIND_PROMPT if blind else PROMPT).format(req=req, root=rel),
            "--output-format", "json", "--no-session-persistence", "--max-budget-usd",
            f"{self._budget if budget_usd is None else budget_usd:g}",
            "--permission-mode", "dontAsk", "--setting-sources", "project", "--strict-mcp-config", "--disable-slash-commands",
            *design_flags(request.name),
            "--tools", *TOOLS,
            "--allowedTools", *reads, f"Write({work})", f"Edit({work})",  # Glob وGrep تخضعان لقاعدة Read لا إذن عام
            "--disallowedTools", *DENY, f"Write(./{rel}/work/REQUEST-*)", f"Edit(./{rel}/work/REQUEST-*)",  # لا يكتب طلبه التالي
            *([] if sub else [f"{tool}(./{rel}/work/{d}/**)" for d in GUARDED for tool in ("Write", "Edit")]),  # ولا حكمًا ولا قراءة
        ]

    def run(self, request: Path, version_root: Path, *, cap_usd: float | None = None,
            tick: Callable[[], None] | None = None) -> ModelResult:
        """cap_usd ما بقي من سقف الأمر: يُحجز للاستدعاء الأصغر منه ومن سقف الاستدعاء الواحد."""
        t0 = time.monotonic()
        reserved = round(self._budget if cap_usd is None else min(self._budget, cap_usd), 4)
        flags = design_flags(request.name)
        asked = {k: flags[flags.index(k) + 1] if k in flags else "" for k in ("--model", "--effort")}
        meta = {"model": asked["--model"] or "default", "effort": asked["--effort"], "reserved_usd": reserved,
                "isolation": isolation() or "none"}
        try:
            cmd = self.command(request, version_root, reserved)
        except ValueError:
            return ModelResult(False, 0.0, 0.0, "مجلد الإصدار خارج المستودع؛ لا يُستدعى النموذج إلا على مخرجات داخل المستودع.", **meta)
        locked = self._locked(request, version_root)
        before = _digest(locked)
        try:
            p = self._spawn(cmd, request, version_root, tick)
        except subprocess.TimeoutExpired:
            # المقطوع أنفق ولا يعلن كم: يُحسب المحجوز حدًّا أعلى (كان يُسجَّل صفرًا فينقص عدّاد الإصدار وسقف الأمر)
            return ModelResult(False, reserved, time.monotonic() - t0,
                               f"تجاوز المهلة ({self._timeout} ث)، وأُوقفت شجرة العملية كاملة؛ كلفته غير معلنة فحُسب المحجوز {reserved:g}$ حدًّا أعلى",
                               cost_known=False, **meta)
        except OSError as e:  # يشمل تعذّر العزل: لا رجوع إلى استدعاء بلا عزل
            return ModelResult(False, 0.0, time.monotonic() - t0, f"{type(e).__name__}: {e}", **meta)
        secs = time.monotonic() - t0
        try:
            data = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {}
        except json.JSONDecodeError:
            data = {}
        cost = float(data.get("total_cost_usd") or 0.0)
        known = "total_cost_usd" in data  # خروج بلا تقرير كلفة (سقوط قبل البدء غالبًا): صفر معلَّم بأنه غير معلن
        full = str(data.get("result") or p.stderr or p.stdout).strip()
        text = full[-400:].strip()
        ok = p.returncode == 0 and not data.get("is_error")
        if _digest(locked) != before:  # نافذة الكتابة تمنع التعديل لا إعادة التسمية: يُكشف هنا ما بُدّل
            ok, text = False, "تغيّر أثناء الاستدعاء ما لا يملكه النموذج (طلبه أو حكم الحَكَم أو قراءة القارئ)؛ راجع work/ قبل أي استئناف."
        usage =data.get("modelUsage")  # مفاتيحه معرّفات النماذج التي عملت فعلًا؛ غيابه لا يُفشل شيئًا
        used = tuple(sorted(str(k) for k in usage)) if isinstance(usage, dict) else ()
        return ModelResult(ok, cost, round(secs, 1), text or f"رمز الخروج {p.returncode}", models_used=used,
                           reply=full[:REPLY_MAX] if ok else "", cost_known=known, **meta)
