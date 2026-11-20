"""التشغيل الآلي بلا توقف للنموذج: حين ينتظر الخط النموذج يُستدعى بالطلب الذي أعلنه الخط في نتيجته ثم يُستأنف الخط، حتى يصل
إلى قرار المالك أو يكتمل. يتوقف عند سقف عدد الاستدعاءات، أو سقف الإنفاق الإجمالي للأمر، أو فشل استدعاء، أو استدعاء لم يغيّر شيئًا
في work/ ولم يغيّر ما ينتظره الخط (فلا يُعاد الطلب نفسه بلا تقدم)، أو استدعاءين على الطلب نفسه ردّ الخط بعدهما بالرسالة نفسها.
ويُسجَّل كل استدعاء وكلفته في `model_calls.jsonl` مع بصمة الطلب والنموذج والجهد وما حُجز له.

التوقف حالة لا اكتمال: يخرج الأمر برمز `STOPPED` ويُكتب سببه في نتيجة الإصدار (`services/outcome.py`)، فتعرضه المنصة تحذيرًا
بسببه وتستأنفه بزر، ولا يضيع السبب بإعادة تشغيلها.

الميزانية تُحجز قبل الاستدعاء: سقف الاستدعاء الواحد هو الأصغر من سقفه المعلن وما بقي من سقف الأمر، فلا يتجاوز مجموع الأمر سقفه
ولو أنفق كل استدعاء حدّه كاملًا؛ وما بقي دون أدنى كلفة نوع الطلب (`min_call_for`) لا يُبدأ به استدعاء يُقطع في منتصفه.

النواة لا تعرف كيف يُستدعى النموذج: المنفذ ModelPort يُحقن من cli، والمحوّل الفعلي في adapters/claude_model.py.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .. import config
from . import outcome
from .pipeline import AWAIT_MODEL, Outcome

STOPPED = outcome.STOPPED

SEP = bytes([0])
MIN_CALL_USD = config.MIN_CALL_USD  # دون هذا لا يُبدأ استدعاء أيًّا كان نوعه: يُنفق ما بقي ثم يُقطع قبل أن يكتب شيئًا
SAME_REQUEST_MAX = 2 # استدعاءان على الطلب نفسه بالجواب نفسه من الخط ثم يتوقف: الثالث لن يختلف ويكلّف مثلهما


@dataclass(frozen=True)
class ModelResult:
    ok: bool
    cost_usd: float
    seconds: float
    summary: str  # آخر الجواب مقصوصًا، للسجل
    model: str = ""  # النموذج المطلوب («default» إن تُرك لإعداد المحوّل)
    effort: str = ""
    models_used: tuple[str, ...] = ()  # المعرّفات الفعلية كما أبلغ بها المحوّل، إن أبلغ
    reserved_usd: float = 0.0  # السقف المحجوز لهذا الاستدعاء: أقصى ما أُنفق إن قُطع بلا كلفة معلنة
    isolation: str = ""  # عزل النظام الذي عملت تحته العملية: «low» أو «none»
    reply: str = ""  # جواب النموذج كاملًا: يُعرض على المالك حين يجيب طلب تعديل بلا تغيير (الخلاصة كانت تبتره من منتصف كلمة)
    cost_known: bool = True  # False: الاستدعاء قُطع أو خرج بلا تقرير كلفة، وcost_usd حدّ أعلى (المحجوز) أو صفر غير معلن


class ModelPort(Protocol):
    def run(self, request: Path, version_root: Path, *, cap_usd: float, tick: Callable[[], None] | None = None) -> ModelResult: ...


def min_call_for(request_name: str) -> float:
    """أدنى ما يُبدأ به استدعاء هذا الطلب: طلب رسم يكلّف دولارات لا يُبدأ بربع دولار ثم يُقطع ويُحسب جولة."""
    return next((usd for prefix, usd in config.MIN_CALL_USD_BY_REQUEST if request_name.startswith(prefix)), MIN_CALL_USD)


def pending_request(work: Path) -> Path | None:
    reqs = sorted(work.glob("REQUEST-*.md"), key=lambda p: p.stat().st_mtime) if work.is_dir() else []
    return reqs[-1] if reqs else None


def work_digest(work: Path) -> str:
    """بصمة ما كتبه النموذج في work/: الأسماء والمحتوى، بلا ملفات الطلبات التي يكتبها الخط."""
    h = hashlib.sha256()
    if work.is_dir():
        for p in sorted(x for x in work.rglob("*") if x.is_file() and not x.name.startswith("REQUEST-")):
            h.update(p.relative_to(work).as_posix().encode("utf-8") + SEP + p.read_bytes() + SEP)
    return h.hexdigest()


def _log(root: Path, request: Path, request_sha256: str, res: ModelResult) -> None:
    rec = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "request": request.name, "request_sha256": request_sha256, **asdict(res)}
    with (root / "model_calls.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _stop(out: Outcome, why: str, req: Path) -> Outcome:
    """توقف التشغيل الآلي والخط ما زال ينتظر النموذج: رمز مميّز وسبب محفوظ في نتيجة الإصدار."""
    message = out.message + "\n" + why
    outcome.write(out.workspace.root, code=STOPPED, message=message, request=req.name, stopped=why)
    return Outcome(STOPPED, message, out.workspace, request=req.name)


def _awaited(out: Outcome) -> Path | None:
    """الطلب الذي ينتظره الخط كما أعلنه في نتيجته. أحدث ملف طلب في work/ ليس هو بالضرورة: طلب مطابق لنصّه السابق لا يُعاد
    كتابته فيبقى وقته قديمًا، فكان الأحدث وقتًا يُستدعى بدل المنتظَر (ملاحظة تعديل مكررة تستدعي الحَكَم بدل الصقل)."""
    if out.request:
        p = out.workspace.work / out.request
        if p.is_file():
            return p
    return pending_request(out.workspace.work)


def run_until_owner(step: Callable[[], Outcome], model: ModelPort | None, max_calls: int, max_usd: float = 15.0,
                    watch: Callable[[Path], None] | None = None, min_call_usd: float | None = None) -> Outcome:
    """يكرر: خطوة الخط، ثم النموذج إن كان هو المنتظَر. لا يتجاوز max_calls استدعاءً ولا max_usd دولارًا في الأمر الواحد.
    min_call_usd يثبّت الحد الأدنى للاستدعاء؛ وبلا قيمة يُحسب من نوع الطلب المنتظَر.
    watch(work) عين الرسّام: يُستدعى دوريًا أثناء عمل النموذج ليبني ويصيّر ما يكتبه فيراه قبل أن يسلّم."""
    out = step()
    calls = 0
    spent = 0.0
    last: tuple[str, str, str] | None = None
    same = 0
    while model is not None and out.code == AWAIT_MODEL:
        req = _awaited(out)
        if req is None:
            break
        if calls >= max_calls:
            return _stop(out, f"بلغ التشغيل الآلي سقف {max_calls} استدعاءات للنموذج في هذا الأمر؛ استأنفه من المنصة أو أعد التشغيل.", req)
        remaining = max_usd - spent
        floor = min_call_for(req.name) if min_call_usd is None else min_call_usd
        if remaining < floor:
            return _stop(out, f"بلغ التشغيل الآلي سقف الإنفاق {max_usd:g}$ في هذا الأمر (أُنفق {spent:.2f}$ وبقي {max(remaining, 0):.2f}$ "
                              f"لا يكفي استدعاءً لـ{req.name}، وأدناه {floor:g}$)؛ استأنفه من المنصة أو أعد التشغيل.", req)
        # النموذج قد يعيد كتابة ملفه بصياغة أخرى فيتغيّر work/ والخط يردّ بالرسالة نفسها على الطلب نفسه: لا تقدم فعلي
        req_sha = hashlib.sha256(req.read_bytes()).hexdigest()
        sig = (req.name, req_sha, out.message)
        same = same + 1 if sig == last else 0
        last = sig
        if same >= SAME_REQUEST_MAX:
            return _stop(out, f"استُدعي النموذج {SAME_REQUEST_MAX} مرات على {req.name} وردّ الخط بالرسالة نفسها، فلا يُعاد آليًا؛ "
                              "راجع الطلب أو ما يشترطه الخط.", req)
        before = work_digest(out.workspace.work)
        if watch is None:
            res = model.run(req, out.workspace.root, cap_usd=remaining)
        else:
            work = out.workspace.work
            getattr(watch, "begin", watch)(work)  # لقطة البداية: ما كان قبل الاستدعاء لا يُعاد تصييره، وعدّاد معايناته يبدأ من صفر
            res = model.run(req, out.workspace.root, cap_usd=remaining, tick=lambda work=work: watch(work))
            watch(work)  # ما كُتب في اللحظة الأخيرة
        _log(out.workspace.root, req, req_sha, res)
        calls += 1
        spent += res.cost_usd
        if not res.ok:
            return _stop(out, f"تعذّر الاستدعاء الآلي للنموذج: {res.summary}", req)
        wrote = work_digest(out.workspace.work) != before
        out = step()
        if not wrote and out.code == AWAIT_MODEL:
            # جواب بلا كتابة قد يكفي الخط (طلب تعديل أجابه النموذج فيعود إلى المالك بجوابه): يُسأل الخط أولًا، وإن بقي ينتظر
            # النموذج فلا تقدم
            return _stop(out, f"لم يكتب النموذج شيئًا في work/ لطلب {req.name}، فلا يُعاد الطلب نفسه آليًا؛ راجع الطلب أو نفّذه يدويًا.", req)
    return out
