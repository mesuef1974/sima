"""سجلّ المشروع للمالك: ماذا جرى على الإصدار ومتى، وأين يقف الآن ومن ينتظر، ونسبة التقدم. قراءة فقط من ملفات الإصدار.

مصادر الأحداث: علامات المراحل (stages/*.json)، وقرارات المفاهيم (decisions.jsonl)، وقرارات بوابات الهوية
(identity_decisions.jsonl)، وطلبات النموذج (work/REQUEST-*.md). الوقت من الحدث نفسه إن سُجّل، وإلا من وقت كتابة الملف.

وبعد التسليم: أحداث البطاقة في دفتر المشروع (قارئ يُحقن من المحوّل، قراءة فقط). الإصدار لا يكتمل عند التسليم بل عند
دمج البطاقة في المشروع، فلا تقول سِمة «اكتمل» والعمل لم يبلغ المشروع بعد.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ..domain.delivery import applied
from . import designer, outcome
from .board import _json, _read_jsonl


def _jsonl(path: Path) -> list[dict]:
    return _read_jsonl(path) if path.is_file() else []

STAGE_AR = {
    "brief": "قُرئ الموجز", "inherited": "ورث الإصدار العلامة المعتمدة من إصدار سابق",
    "adopted": "دخلت الخط علامة واتجاه اعتمدهما المالك خارجه", "designer_sketches": "استُلمت صفحة السكتشات من المصمّم الخارجي", "research": "اكتمل البحث وقراءة السوق",
    "diverge": "رسم النموذج المفاهيم المتباعدة", "render": "صُيّرت المفاهيم وفُحصت آليًا", "critique": "اكتملت جولات النقد",
    "preview": "بُنيت ورقة المعاينة", "name_check": "سُجّل تحقق الاسم", "strategy": "اعتُمدت المنصة الاستراتيجية",
    "directions_board": "بُنيت لوحة الاتجاهات بعد فحصها", "directions": "اعتُمد اتجاه الهوية", "package": "بُنيت حزمة العلامة",
    "identity_build": "بُنيت الهوية الكاملة ودليلها", "identity": "اعتُمد دليل الهوية وأُغلق الإصدار", "deliver": "سُلّمت المخرجات إلى المشروع", "deliver_pending": "أُنشئت بطاقة التسليم في دفتر المشروع",
    "shortlist": "حكم الحَكَم المستقل بمعيار الاحتراف واختير أفضل ثلاثة للعرض", "owner_feedback": "أُعيد الرسم بملاحظاتك",
    "medium_epoch": "بدأ رسم جديد بالوسيط الذي اخترته",
    "novelty": "قيست جِدّة الأفكار أمام ما رفضتَه سابقًا",
    "thumbs": "رُسمت مصغّرات الأفكار وقُرئت قراءة عمياء واختير منها ما يُرسم",
    "style_board": "رُسمت عينات الطابع الست وعُرضت عليك", "style_epoch": "بدأ الرسم بالطابع الذي اخترته",
}
REQUEST_AR = {"diverge": "رسم المفاهيم", "strategy": "كتابة المنصة الاستراتيجية", "directions": "ثلاثة اتجاهات للهوية",
              "icons": "مجموعة الأيقونات", "revise": "تعديل الهوية بملاحظتك",
              "judge": "التحكيم المستقل بمعيار الاحتراف", "refine": "صقل المفاهيم بعد التحكيم", "refine-owner": "إعادة الرسم بملاحظاتك",
              "style": "عينات الطابع البصري", "fix": "تصحيح صيغة ملف كتبه النموذج",
              "blind": "قراءة عمياء مستقلة قبل الحَكَم", "refine-blind": "تصحيح قراءة خاطئة قبل الحَكَم",
              "thumbs": "مصغّرات الأفكار", "blind-thumbs": "قراءة عمياء لمصغّرات الأفكار",
              "designer-sketches": "صفحة السكتشات", "designer-vector": "بناء السكتش المختار متجهًا", "designer-fix": "تصحيح ما ردّه الفحص"}
MEDIUM_AR = {"abstract_mark": "علامة مجردة", "wordmark": "علامة كلامية", "emblem": "شارة", "pattern": "نمط"}
GATE_AR = {"strategy": "المنصة الاستراتيجية", "directions": "اتجاه الهوية", "book": "دليل الهوية"}
DEFAULT_REASONS = {"اعتماد من منصة سِمة", "اختير مع اعتماد المنصة الاستراتيجية"}
VERDICT_AR = {"approved": "اعتمدت", "revise": "طلبت تعديل", "rejected": "رفضت", "switch_medium": "طلبت رسمًا جديدًا بوسيط"}

BASE_FLOW = ("brief", "research", "diverge", "render", "critique", "preview", "name_check", "package")
DRAWN_ONLY = ("critique", "preview")  # علامة اعتُمدت خارج الخط لا تمرّ بالنقد ولا بورقة المعاينة
ADOPTED_AR = {"diverge": "قُرئت العلامة المعتمدة من بيان الاعتماد", "render": "صُيّرت العلامة المعتمدة وفُحصت عند حدّها المعلن",
              "directions_board": "بُنيت لوحة الاتجاه المعتمد بعد فحصه"}
IDENTITY_FLOW = ("strategy", "directions", "identity_build", "identity")
FLOW_AR = {"brief": "الموجز", "research": "البحث", "diverge": "المفاهيم", "render": "الفحص", "critique": "النقد", "preview": "المعاينة",
           "name_check": "تحقق الاسم", "package": "الحزمة", "strategy": "المنصة", "directions": "الاتجاه", "identity_build": "بناء الهوية",
           "identity": "الدليل", "deliver": "التسليم", "landed": "الدمج في المشروع"}

# أحداث دفتر المشروع: (النص، من ينتظر بعده). الاعتماد على الطلب قرار المالك، فإذا فُتح الطلب صار المنتظَر هو المالك.
CARD_AR: dict[str, tuple[str, str]] = {
    "created": ("أُنشئت بطاقة التسليم في دفتر المشروع", "project"),
    "ready": ("البطاقة جاهزة في دفتر المشروع ولم يلتقطها أحد بعد؛ شغّل مشغّل المشروع أو أبلغ جلسته", "project"),
    "claimed": ("التُقطت البطاقة ويُنفَّذ العمل عليها في المشروع", "project"),
    "coded": ("أُنجز العمل على البطاقة وأُودع", "project"),
    "prepush_failed": ("فشل الفحص المحلي في المشروع؛ يلزم إصلاح قبل فتح الطلب", "project"),
    "prepush_ok": ("نجح الفحص المحلي في المشروع", "project"),
    "pr_opened": ("فُتح طلب الدمج؛ ينتظر فحوص CI واعتمادك على الطلب", "owner"),
    "ci_green": ("نجحت فحوص CI على الطلب؛ ينتظر اعتمادك", "owner"),
    "approved": ("اعتُمد الطلب؛ ينتظر طابور الدمج", "project"),
    "merged": ("دُمجت الهوية في المشروع", "project"),
    "deployed": ("نُشرت الهوية في المشروع", "project"),
}
LANDED = ("merged", "deployed")
OWNER_WAITS = ("pr_opened", "ci_green")
CardReader = Callable[[str, str], list[dict]]
CardsReader = Callable[[str], dict[str, list[dict]]]
PR_URL = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)")
HEAD = re.compile(r"الرأس ([0-9a-f]{7,40})")


def approval(events: list[dict]) -> dict | None:
    """إن كانت البطاقة تنتظر اعتماد المالك على طلبها: المستودع ورقم الطلب والرأس، ليُبنى أمر سطر الاعتماد."""
    if not events or events[-1].get("event") not in OWNER_WAITS:
        return None
    url = head = None
    for c in reversed(events):
        text = f"{c.get('url', '')} {c.get('note', '')}"
        url = url or PR_URL.search(text)
        h = c.get("head") or (m.group(1) if (m := HEAD.search(text)) else "")
        head = head or (str(h)[:8] if h else None)
    if not url or not head:
        return None
    return {"repo": url.group(1), "pr": int(url.group(2)), "head": head}


def _card_text(c: dict) -> str:
    text, _ = CARD_AR.get(str(c.get("event")), (str(c.get("event")), "project"))
    extra = c.get("url") or (c.get("note") if c.get("event") == "pr_opened" else "")
    return text + (f" ({str(extra)[:200]})" if extra else "")


def related_cards(cards: dict[str, list[dict]], delivered: str, wordmark: str) -> dict[str, list[dict]]:
    """بطاقات المشروع اللاحقة للهوية: أُنشئت بعد بطاقة التسليم، وتذكر العلامة «…» أو البطاقة نفسها، أو «الهوية» في عنوانها
    (بطاقة «توحيد لوحة الإدارة مع الهوية» لا تذكر اسم العلامة لكنها من تطبيق الهوية)."""
    first = cards.get(delivered, [{}])[0].get("at", "")
    out = {}
    for cid, evs in cards.items():
        if cid == delivered or not evs:
            continue
        head = evs[0]
        title = str(head.get("title", ""))
        blob = f"{title} {head.get('body', '')}"
        if str(head.get("at", "")) >= first and (f"«{wordmark}»" in blob or delivered in blob or "هوية" in title):
            out[cid] = evs
    return out


def _mtime(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat(timespec="seconds")


def _request_label(stem: str) -> str:
    name = stem.removeprefix("REQUEST-")
    m = re.fullmatch(r"critique-r(\d+)", name)
    if m:
        return f"جولة النقد {m.group(1)}"
    return REQUEST_AR.get(name, name)


def _first_line(text: str) -> str:
    return next((ln.strip() for ln in str(text).splitlines() if ln.strip()), "")[:400]


def flow(identity: bool) -> tuple[str, ...]:
    """خطوات الإصدار بترتيب الخط نفسه: المنصة الاستراتيجية قبل الرسم، والاتجاه بعد تحقق الاسم وقبل الحزمة (ب15: كانت خطوات
    الهوية تُلحق بعد الحزمة فيظهر «الحزمة» قبل المنصة والاتجاه)."""
    if not identity:
        return (*BASE_FLOW, "deliver", "landed")
    return ("brief", "research", "strategy", "diverge", "render", "critique", "preview", "name_check", "directions", "package",
            "identity_build", "identity", "deliver", "landed")


def steps_for(v: Path) -> tuple[str, ...]:
    """خطوات هذا الإصدار: نموذج واحد للسجل ولصفحة المشاريع (م6 د). علامة من خارج الخط لا تمرّ بالنقد ولا بورقة المعاينة."""
    adopted = (v / "stages" / "adopted.json").is_file() or designer.frozen_enabled(v)
    return tuple(s for s in flow(bool(_json(v / "brief.json").get("identity"))) if not (adopted and s in DRAWN_ONLY))


def progress(v: Path, done: set[str]) -> dict:
    steps = steps_for(v)
    current = next((s for s in steps if s not in done), None)
    return {"done": len([s for s in steps if s in done]), "total": len(steps), "current": current,
            "steps": [{"key": s, "label": FLOW_AR.get(s, s), "status": "done" if s in done else ("current" if s == current else "pending")}
                      for s in steps]}


def _git_landed(v: Path, landed: Callable[[dict], bool] | None) -> bool:
    """دمج مسار الفرع المحلي (بلا دفتر) يُعرف من git: كاشف يُحقن من الحافة ولا يرمي."""
    deliver = _json(v / "stages" / "deliver.json")
    if landed is None or applied(deliver) or not deliver.get("head") or not deliver.get("repo"):
        return False
    try:
        return bool(landed(deliver))
    except OSError:
        return False


def reached(v: Path, read_card: CardReader | None = None, landed: Callable[[dict], bool] | None = None) -> set[str]:
    """ما أُنجز من خطوات الإصدار: علامات مراحله، و«الدمج في المشروع» من علامة التسليم في مكانه أو من دفتر المشروع
    أو من git لتسليم الفرع المحلي."""
    stages = v / "stages"
    done = {f.stem for f in stages.glob("*.json")} if stages.is_dir() else set()
    if (applied(_json(stages / "deliver.json")) or any(c.get("event") in LANDED for c in _card(v, read_card))
            or _git_landed(v, landed)):
        done.add("landed")
    return done


def latest_version(project_dir: Path) -> Path | None:
    vs = [p for p in project_dir.iterdir() if p.is_dir() and re.fullmatch(r"v\d+", p.name)] if project_dir.is_dir() else []
    return max(vs, key=lambda p: int(p.name[1:]), default=None)


def _version_start(stages: Path) -> str:
    """بداية الإصدار: وقت علامة الموجز أو الوراثة، وهما أول ما يُكتب فيه. علامة `adopted` تُكتب قبل الموجز في إصدار الاعتماد
    الخارجي، لكنها في إصدار موروث منسوخة من سلفه بوقته: لا تُحسب بدايةً له (ب15)، وإلا لم يوسَم شيء «من الإصدار السابق»."""
    times = []
    for name in (("brief", "inherited") if (stages / "inherited.json").is_file() else ("brief", "adopted")):
        f = stages / f"{name}.json"
        if f.is_file():
            times.append(str(_json(f).get("at") or "") or _mtime(f))
    return min(times, default="")


def _owner_choices(v: Path) -> list[dict]:
    """قرارات المالك خارج دفتر المفاهيم وبوابات الهوية: الطابع، والسكتش وتطويره ورفض صفحته وردّ متجهه (م6 ز: صفحة القرارات
    كانت تعرض قرارات المفاهيم وحدها)."""
    out = []

    def said(d: dict, key: str) -> str:
        return f" — ملاحظتك: {d[key]}" if str(d.get(key) or "").strip() else ""

    for d in _jsonl(v / "style_decisions.jsonl"):
        names = "، ".join(str(s) for s in d.get("styles") or [])
        out.append({"at": str(d.get("at", "")), "who": "owner", "text": f"اخترت الطابع البصري {names}" + said(d, "note")})
    for d in _jsonl(v / "designer_decisions.jsonl"):
        n, reason = d.get("sketch"), str(d.get("reason") or "")
        if d.get("rejected"):
            text = f"رفضت صفحة السكتشات: {reason}"
        elif d.get("develop"):
            text = f"طلبت تطوير السكتش {n} بصفحة حوله" + said(d, "note")
        elif d.get("rebuild"):
            text = f"رددت متجه السكتش {n}: {reason}"
        else:
            text = f"اخترت السكتش {n}" + said(d, "note")
        out.append({"at": str(d.get("at", "")), "who": "owner", "text": text})
    return out


def _card(v: Path, read_card: CardReader | None) -> list[dict]:
    deliver = _json(v / "stages" / "deliver.json")
    if read_card is None or not deliver.get("card_id") or not deliver.get("repo"):
        return []
    try:
        return read_card(str(deliver["repo"]), str(deliver["card_id"]))
    except OSError:
        return []


def timeline(v: Path, waiting: dict | None = None, job: dict | None = None, read_card: CardReader | None = None,
             read_cards: CardsReader | None = None, landed: Callable[[dict], bool] | None = None) -> dict:
    """أحداث الإصدار الأحدث أولًا، والحالة الآن، والتقدم. waiting: بند صندوق القرارات إن كان المالك هو المنتظَر.
    read_card: قارئ دفتر المشروع (المستودع، البطاقة) ليُرى ما جرى بعد التسليم."""
    events: list[dict] = []
    stages = v / "stages"
    done: set[str] = set()
    adopted = (stages / "adopted.json").is_file() or designer.frozen_enabled(v)  # مسار المصمّم الخارجي لا يرسم في الخط أيضًا
    if stages.is_dir():
        for f in stages.glob("*.json"):
            done.add(f.stem)
            data = _json(f)
            at = str(data.get("at") or data.get("checked_at") or "") or _mtime(f)
            text = (ADOPTED_AR if adopted else {}).get(f.stem) or STAGE_AR.get(f.stem, f.stem)
            if f.stem == "directions_board" and (_json(v / "brief.json").get("identity") or {}).get("directions") == "three":
                text = STAGE_AR[f.stem]  # ثلاثة اتجاهات فوق علامة من خارج الخط: اللوحة ليست لوحة اتجاه واحد
            if f.stem == "directions" and data.get("option"):
                text += f" ({data['option']})"
            if f.stem == "deliver" and data.get("in_place"):
                text = f"طُبّقت الهوية في مستودع سِمة نفسه (النقطة {str(data.get('commit', ''))[:8]})؛ لا بطاقة ولا دمج خارجي"
            if f.stem == "deliver" and data.get("manual"):
                text = (f"طبّقت جلسة المشروع الهوية يدويًّا ودمجتها في {Path(str(data.get('repo', ''))).name} "
                        f"(النقطة {str(data.get('commit', ''))[:8]})؛ بلا بطاقة ولا مشغّل")
            # تحقق الاسم يسجّله المالك بيده: قراره لا خطوة آلية (م6 ز)
            events.append({"at": at, "who": "owner" if f.stem == "name_check" else "script", "text": text})
    events += _owner_choices(v)
    for d in _jsonl(v / "decisions.jsonl"):
        verdict = VERDICT_AR.get(str(d.get("verdict")), str(d.get("verdict")))
        cid = d.get("concept_id") or ""
        reason = str(d.get("reason") or "")
        what = f"«{MEDIUM_AR.get(str(d.get('medium')), d.get('medium'))}»" if d.get("verdict") == "switch_medium" else f"المفهوم {cid}"
        events.append({"at": d.get("at", ""), "who": "owner", "text": f"{verdict} {what}".strip() + (f": {reason}" if reason else "")})
    for d in _jsonl(v / "identity_decisions.jsonl"):
        verdict = VERDICT_AR.get(str(d.get("verdict")), str(d.get("verdict")))
        gate = GATE_AR.get(str(d.get("gate")), str(d.get("gate")))
        opt = f" واخترت {d['option']}" if d.get("option") else ""
        reason = str(d.get("reason") or "")
        if reason == designer.RULE:  # مرّت بقاعدة المسار لا بقرار: لا تُنسب إلى المالك
            events.append({"at": d.get("at", ""), "who": "script", "text": f"مرّت {gate} بلا بوابة بقاعدة مسار المصمّم الخارجي؛ تراها في الدليل."})
            continue
        if reason in DEFAULT_REASONS:  # نص يكتبه الخط حين لا يكتب المالك شيئًا؛ ليس ملاحظته
            reason = ""
        events.append({"at": d.get("at", ""), "who": "owner", "text": f"{verdict} {gate}{opt}" + (f" — ملاحظتك: {reason}" if reason else "")})
    for c in _jsonl(v / "model_calls.jsonl"):
        req = _request_label(str(c.get("request", "")).removesuffix(".md"))
        state = "أنجز" if c.get("ok") else "تعذّر"
        events.append({"at": c.get("at", ""), "who": "model",
                       "text": f"{state} النموذج آليًا: {req} ({c.get('seconds', 0)} ث، {float(c.get('cost_usd') or 0):.2f}$) — {c.get('summary', '')}"[:400]})
    card = _card(v, read_card)
    for c in card:
        events.append({"at": str(c.get("at", "")), "who": "project", "text": f"البطاقة {c.get('card', '')}: {_card_text(c)}"})
    follow: dict[str, list[dict]] = {}
    deliver_m = _json(stages / "deliver.json") if stages.is_dir() else {}
    if read_cards and deliver_m.get("repo") and deliver_m.get("card_id"):
        brief_m = _json(v / "brief.json")
        wordmark = str(brief_m.get("name_short") or brief_m.get("name_ar") or "")
        try:
            follow = related_cards(read_cards(str(deliver_m["repo"])), str(deliver_m["card_id"]), wordmark) if wordmark else {}
        except OSError:
            follow = {}
        for cid, evs in follow.items():
            title = str(evs[0].get("title", ""))[:80]
            for c in evs:
                events.append({"at": str(c.get("at", "")), "who": "project", "text": f"بطاقة لاحقة {cid} «{title}»: {_card_text(c)}"})
    if applied(deliver_m) or any(c.get("event") in LANDED for c in card):  # المسلَّم في مكانه أو يدويًّا مدموج بنقطته
        done.add("landed")
    elif _git_landed(v, landed):  # فرع محلي بلا دفتر: الدمج يُعرف من git
        done.add("landed")
        events.append({"at": "", "who": "project", "text": f"دُمج تسليم {deliver_m.get('branch', '')} في الفرع الرئيس (اكتُشف من git)."})
    work = v / "work"
    requests = sorted(work.glob("REQUEST-*.md"), key=lambda p: p.stat().st_mtime) if work.is_dir() else []
    for r in requests:
        ext = r.name.startswith("REQUEST-designer-")  # تُرسله الجلسة إلى المصمّم الخارجي بأمر المالك، لا نموذج الخط
        events.append({"at": _mtime(r), "who": "designer" if ext else "model",
                       "text": f"طُلب من {'المصمّم الخارجي' if ext else 'النموذج'}: {_request_label(r.stem)}"})
    # الإصدار الموروث يحمل علامات سلفه وقراراته وطلباته بأوقاتها: تبقى في السجل موسومةً بمصدرها لا مختلطةً بأحداثه
    start = _version_start(stages)
    if start:
        for e in events:
            if e["at"] and e["at"] < start:
                e["text"] += " (من الإصدار السابق)"
    # الأحدث أولًا؛ وما تساوى وقته يبقى بترتيب تسجيله معكوسًا، فيظهر الأخير تسجيلًا أولًا
    order = sorted(range(len(events)), key=lambda i: (events[i]["at"], i), reverse=True)
    events = [events[i] for i in order]

    run = _json(v / "run.json")
    prog = progress(v, done)
    current = prog["current"]
    last_stage = max((f.stat().st_mtime for f in stages.glob("*.json")), default=0.0) if stages.is_dir() else 0.0
    # >= لا >: طلب يُكتب في النبضة نفسها بعد آخر علامة (ساعة ملفات Windows خشنة) ما زال معلّقًا
    pending_req = [r for r in requests if r.stat().st_mtime >= last_stage]
    # نتيجة الخط المكتوبة في الإصدار هي المرجع لمن يُنتظر وللتوقف وسببه؛ ما بعدها استنتاج لإصدار أقدم من العلامة
    o = outcome.current(v) if not run.get("closed") else None
    running = bool(job and job.get("state") == "running")
    if running:
        now = {"who": "script", "text": "الخط يعمل الآن في الخلفية.", "since": job.get("started", "")}
    elif waiting and waiting.get("kind") == "stalled":
        now = {"who": "owner", "state": "stopped", "text": f"الخط واقف عندك بلا قرار في بطاقة: {_first_line(waiting.get('message', ''))}",
               "since": o["at"] if o else "", "after": waiting.get("after", ""), "resume": True}
    elif waiting:
        now = {"who": "owner", "text": f"ينتظر قرارك: {waiting.get('title', '')}", "since": "", "after": waiting.get("after", "")}
    elif o is not None and o["stopped"]:
        now = {"who": "model", "state": "stopped", "text": f"توقّف التشغيل الآلي عند «{_request_label(Path(o['request']).stem)}»: {o['stopped']}",
               "since": o["at"], "resume": True}
    elif o is not None and o["who"] == "error":
        now = {"who": "script", "state": "stopped", "text": f"توقّف الخط بخطأ: {_first_line(o['message'])}", "since": o["at"], "resume": True}
    elif o is not None and o["who"] == "model":
        now = {"who": "model", "state": "stopped", "since": o["at"], "resume": True,
               "text": f"الخط ينتظر النموذج عند «{_request_label(Path(o['request']).stem)}» ولم يُستدعَ آليًا (الاستدعاء الآلي معطّل أو غير "
                       "مأذون لهذا المشروع). الاستئناف يستدعيه إن كان مفعّلًا."}
    elif o is not None and o["who"] == "designer":
        now = {"who": "designer", "text": f"ينتظر المصمّم الخارجي: {_request_label(Path(o['request']).stem)}. يُرسل من صندوق المصمّم ويُستلم ردّه فيه.",
               "since": o["at"]}
    elif not run.get("closed") and outcome.superseded(v):
        now = {"who": "script", "state": "stopped", "text": "سُجّل قرار أو استلام ولم يُستأنف الخط بعده.", "since": "", "resume": True}
    elif current == "deliver" and run.get("closed"):
        now = {"who": "owner", "text": "الإصدار مكتمل ومعتمد؛ بقي تسليمه إلى مشروعه بأمر sima deliver.", "since": ""}
    elif current == "landed":
        last = card[-1] if card else {}
        text, who = CARD_AR.get(str(last.get("event")), ("سُلّمت البطاقة ولا يُقرأ دفتر المشروع؛ تحقق منه في المستودع.", "project"))
        now = {"who": who, "text": text, "since": str(last.get("at", "")), "approval": approval(card)}
    elif pending_req and pending_req[-1].name.startswith("REQUEST-designer-"):
        now = {"who": "designer", "text": f"ينتظر المصمّم الخارجي: {_request_label(pending_req[-1].stem)}. تُرسله الجلسة بأمرك وتستلم ناتجه.",
               "since": _mtime(pending_req[-1])}
    elif pending_req:
        now = {"who": "model", "text": f"ينتظر النموذج: {_request_label(pending_req[-1].stem)}. يُستدعى آليًا عند الاستئناف إن كان التشغيل الآلي مفعّلًا.",
               "since": _mtime(pending_req[-1]), "resume": True}
    elif current is None:
        now = {"who": "script", "text": "اكتمل كل شيء في هذا الإصدار.", "since": ""}
        waiting_follow = [(cid, evs) for cid, evs in follow.items() if evs[-1].get("event") in OWNER_WAITS]
        if waiting_follow:
            cid, evs = waiting_follow[-1]
            text, who = CARD_AR[str(evs[-1]["event"])]
            now = {"who": who, "text": f"الهوية مدموجة؛ وبطاقة لاحقة {cid} «{str(evs[0].get('title', ''))[:60]}»: {text}",
                   "since": str(evs[-1].get("at", "")), "approval": approval(evs)}
    else:
        now = {"who": "script", "text": f"جاهز للاستئناف عند مرحلة «{FLOW_AR.get(current, current)}».", "since": "", "resume": True}
    now["resume"] = bool(now.get("resume")) and not run.get("closed") and not running  # الاستئناف لإصدار مفتوح بلا تشغيل جارٍ
    return {
        "version": v.name, "key": run.get("key", ""), "closed": bool(run.get("closed")), "now": now, "events": events,
        "progress": prog,
    }


def project_timeline(out_dir: Path, project: str, waiting: dict | None = None, job: dict | None = None,
                     read_card: CardReader | None = None, read_cards: CardsReader | None = None,
                     landed: Callable[[dict], bool] | None = None) -> dict | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", project):
        return None
    v = latest_version(out_dir / project)
    if v is None or not (v / "run.json").is_file():
        return None
    return {"project": project, **timeline(v, waiting, job, read_card, read_cards, landed)}
