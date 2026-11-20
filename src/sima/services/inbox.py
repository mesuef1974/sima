"""صندوق قرارات المالك في منصة سِمة: ما ينتظر قراره في كل مشروع، وتطبيق قراره مربوطًا بمفتاح التشغيل المعروض.

على نمط اعتماد مشغّل مدرسة الشحانية: لا قرار على ما لم يُعرض. المنصة تحمل مفتاح التشغيل والإصدار الذي رآه المالك،
وأي تغيّر بينهما (إصدار أحدث، أو قرار سبقه، أو حزمة اكتملت) يرفض القرار ويطلب تحديث الصفحة. لا شبكة ولا تخمين.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

import yaml

from .. import config
from ..domain import Medium, NameStatus
from ..domain.brief import load_brief
from ..domain.decision import Verdict
from ..domain.identity import GATE_AR, Gate
from ..domain.run import RunKey
from . import adopt, designer, outcome, style
from .identity_protocol import digest, directions_digest, read_directions, read_strategy, revise_reply, strategy_path
from .identity_protocol import ledger as id_ledger
from .ledger import Ledger
from .namecheck import NAME_SOURCES, SOURCE_KEYS, read_name_check, record_name_check, result_problem
from .pipeline import record_decision, record_switch
from .protocol import concepts_digest, merged_digest, read_concept_svgs, read_concepts, read_small_svgs
from .workspace import Workspace

MEDIUM_AR = {"abstract_mark": "علامة مجردة", "wordmark": "علامة كلامية", "emblem": "شارة", "pattern": "نمط"}
VERDICT_AR = {Verdict.APPROVED: "اعتُمد", Verdict.REJECTED: "رُفض", Verdict.REVISE: "طُلب تعديل", Verdict.SWITCH: "اختير وسيط"}
MIN_REASON = 3
# أطول ما يُقبل من نص المالك في كل حقل. الزائد يُرفض ولا يُقصّ (م8): كانت ثلاث ملاحظات تُقصّ بصمت قبل تسجيلها. المنصة
# ترسل هذه الحدود في `/api/state` فتضعها الواجهة على حقولها
LIMITS = {"decide": 500, "medium": 800, "identity": 1200, "note": 600, "reason": 800}


class InboxError(ValueError):
    """قرار مرفوض بسبب واضح للمالك (يُعرض كما هو)."""


def _within(text: str, field: str) -> str:
    """نص المالك يدخل كما كتبه أو لا يدخل."""
    if len(text) > LIMITS[field]:
        raise InboxError(f"النص أطول من الحد ({len(text)} حرفًا من {LIMITS[field]})؛ اختصره ثم أعد الإرسال، فلا يُقصّ منه شيء.")
    return text


def _versions(project_dir: Path) -> list[tuple[int, Path]]:
    out = []
    for p in project_dir.iterdir() if project_dir.is_dir() else []:
        if p.is_dir() and p.name.startswith("v") and p.name[1:].isdigit():
            out.append((int(p.name[1:]), p))
    return sorted(out)


def _workspace(v: Path) -> tuple[Workspace, dict]:
    run = json.loads((v / "run.json").read_text(encoding="utf-8"))
    key = RunKey(project=str(run["project"]), brief_hash=str(run["brief_hash"]), seed=int(run["seed"]))
    return Workspace(root=v, key=key, version=int(run["version"])), run


def _item(out_dir: Path, project_dir: Path) -> dict | None:
    """ما ينتظر المالك في آخر إصدار للمشروع، أو None.

    المرجع نتيجة الخط المكتوبة في الإصدار (`services/outcome.py`): إن وقف الخط عند المالك عُرضت بطاقة بوابته بمحتواها،
    وإن وقف عنده بلا قرار يُعرض في بطاقة (أو تغيّر المعروض بعد وقوفه) عُرض ما وقف عنده مع زر الاستئناف، فلا يعلق إصدار
    بلا بطاقة؛ وإن لم يكن المالك هو المنتظَر فلا بطاقة. وحين لا نتيجة سارية (قرار سُجّل ولم يُستأنف الخط بعد، أو إصدار أقدم
    من العلامة) يُستنتج المنتظَر من ملفات الإصدار كما كان."""
    versions = _versions(project_dir)
    if not versions or not (versions[-1][1] / "run.json").is_file():
        return None
    n, v = versions[-1]
    ws, run = _workspace(v)
    if run.get("closed"):
        return None
    rel = f"{project_dir.name}/v{n}"
    base = {"project": project_dir.name, "version": n, "key": ws.key.key, "brief": str(run.get("brief_source", "")),
            "preview": f"{rel}/preview.html" if (v / "preview.html").is_file() else "", "_ledger": id_ledger(ws)}
    o = outcome.current(v)
    if o is None:
        return _derived(ws, v, base, rel)
    if o["who"] != "owner":
        # تحقق الاسم خطوة المالك وحده ولا تتوقف على ما يفعله الخط: يبقى متاحًا بعد اعتماد المفهوم والخط عند غيره
        return _name_gate(ws, v, base, rel) if Ledger(ws.ledger_path).approved() is not None else None
    build = GATE_CARDS.get(o["gate"])
    item = build(ws, v, base, rel) if build else None
    if item is not None and (not o["digest"] or item.get("digest") == o["digest"]):
        return item
    return {**base, "kind": "stalled", "gate": o["gate"], "digest": o["digest"], "message": o["message"]}


def _derived(ws: Workspace, v: Path, base: dict, rel: str) -> dict | None:
    """المنتظَر مستنتجًا من ملفات الإصدار، بترتيب مراحل الخط."""
    gate = _strategy_gate(ws, v, base, rel)
    if gate is not None:
        return gate
    approved = Ledger(ws.ledger_path).approved()
    if approved is None and designer.frozen_enabled(v):
        return _sketch_gate(ws, v, base, rel)  # مسار المصمّم الخارجي: لا عينات طابع ولا مفاهيم مرسومة في الخط
    if approved is None and config.STYLE_GATE and style.choices(ws) and int(ws.read_marker("style_epoch").get("choices", 0)) != len(style.choices(ws)):
        return None  # اختيار طابع جديد لم يُرسم به بعد: ما يُعرض الآن رُسم قبله
    if approved is None and config.STYLE_GATE and style.current(ws) is None:
        return _style_gate(ws, v, base, rel)
    if approved is None or approved.concept_id not in {c.id for c in read_concepts(ws)}:
        return _concepts_gate(ws, v, base, rel)
    name = _name_gate(ws, v, base, rel)
    if name is not None:
        return name
    if designer.frozen_enabled(v):
        sheet, _ = designer.read_sheet(ws)
        if sheet is not None and designer.pending_rebuild(ws, sheet) is not None:
            return None  # ردّ المالك المتجه المبني: الدليل القائم مبني على المردود، والدور للمصمّم حتى يصل تسليم جديد
    return _directions_gate(ws, v, base, rel) or _book_gate(ws, v, base, rel)


def _style_gate(ws: Workspace, v: Path, base: dict, rel: str) -> dict | None:
    """بوابة الطابع: لا تظهر إلا حين يصل الخط إليها بالعينات الحالية نفسها."""
    dg = style.digest(ws)
    if ws.read_marker("style_board").get("digest") != dg:
        return None
    return {**base, "kind": "style", "digest": dg, "max": config.STYLE_PICK_MAX,
            "styles": [{"id": sid, "name": name, "principle": principle, "img": f"{rel}/work/styles/{sid}.svg"}
                       for sid, (name, principle) in style.catalog().items()]}


def _concepts_gate(ws: Workspace, v: Path, base: dict, rel: str) -> dict | None:
    concepts = read_concepts(ws)
    if not base["preview"] or not concepts:
        return None
    # البطاقة لا تظهر إلا حين يصل الخط فعلًا إلى قرار المالك على هذه الرسوم بعينها: معاينتها مبنية لمحتواها الحالي
    # (بعد الحَكَم). رسم جديد أو صقل جارٍ يغيّر المحتوى فتختفي البطاقة حتى يعود الخط إليه.
    if ws.read_marker("preview").get("digest") != merged_digest(read_concept_svgs(ws, concepts), read_small_svgs(ws, concepts)):
        return None
    ledger = Ledger(ws.ledger_path)
    # ما قبل آخر إعادة رسم لا يخص الرسوم المعروضة الآن
    handled = int(ws.read_marker("owner_feedback").get("handled", 0))
    verdicts = {d.concept_id: VERDICT_AR[d.verdict] for d in ledger.read()[handled:] if d.concept_id}
    sl = ws.read_marker("shortlist")
    if sl.get("ids"):
        by_id = {c.id: c for c in concepts}
        concepts = [by_id[i] for i in sl["ids"] if i in by_id]
    cur = ledger.lock().current()
    return {**base, "kind": "concepts", "digest": concepts_digest(ws), "below_bar": bool(sl.get("below_bar")), "bar": config.JUDGE_MIN_TOTAL,
            "medium": cur.value if cur else "", "mediums": [{"id": k, "ar": v} for k, v in MEDIUM_AR.items()],
            "concepts": [{
        "id": c.id, "name": c.name, "medium_ar": MEDIUM_AR.get(c.medium.value, c.medium.value), "sentence": c.sentence,
        "img": f"{rel}/work/concepts/{c.id}.svg" if (ws.concepts_dir / f"{c.id}.svg").is_file() else "",
        "last": verdicts.get(c.id, ""), "score": (sl.get("scores") or {}).get(c.id),
        "passed": c.id in (sl.get("passed") or []),
    } for c in concepts]}


def _name_gate(ws: Workspace, v: Path, base: dict, rel: str) -> dict | None:
    """تحقق الاسم: يُنتظر ما لم يُسجَّل «متاح» لاسم الموجز نفسه. تحقق موروث لاسم آخر لا يكفي الخط (`_stage_name_check`)،
    فلا يكفي البطاقة (كانت تفحص الحالة وحدها فيقف الخط بلا بطاقة)."""
    nc = read_name_check(ws)
    brief = json.loads((v / "brief.json").read_text(encoding="utf-8")) if (v / "brief.json").is_file() else {}
    name = str(brief.get("name_short") or brief.get("name_ar") or (nc.name if nc else base["project"]))
    same = nc is not None and nc.name == name
    if same and nc.status is NameStatus.CLEAR:
        return None
    approved = Ledger(ws.ledger_path).approved()
    note = nc.note if same else (f"سُجّل تحقق سابق لاسم آخر «{nc.name}»؛ الاسم الآن «{name}» ويلزمه تحققه." if nc else "")
    return {**base, "kind": "name_check", "concept": approved.concept_id if approved else "", "name": name,
            "status": nc.status.value if same else "", "note": note,
            "sources": [{"key": k, "label": label, "url": url.replace("{q}", quote(name)), "hint": hint.replace("{q}", name)}
                        for k, (label, url, hint) in zip(SOURCE_KEYS, NAME_SOURCES, strict=True)]}


def _sketch_gate(ws: Workspace, v: Path, base: dict, rel: str) -> dict | None:
    """صفحة سكتشات المصمّم الخارجي: تظهر حين يصل الخط إليها بمحتواها الحالي ولم يُختر منها بعد ولم تُرفض."""
    sheet, _ = designer.read_sheet(ws)
    if sheet is None or ws.read_marker(designer.MARKER).get("digest") != sheet.digest or designer.current(ws, sheet) is not None:
        return None
    if designer.rejection(ws, sheet) is not None or designer.development(ws, sheet) is not None:  # رُفضت أو طُلب تطوير سكتش منها
        return None
    return {**base, "kind": "sketches", "digest": sheet.digest, "img": f"{rel}/designer/{sheet.image}", "source": sheet.source,
            "sketches": [{"id": i, "idea": idea, "pick": i in sheet.picks} for i, idea in sheet.sketches]}


def _gate(base: dict, gate: Gate, dg: str, **extra) -> dict:
    return {**base, "kind": "identity", "gate": gate.value, "gate_ar": GATE_AR[gate], "digest": dg,
            "history": [{"verdict": d.verdict, "option": d.option, "reason": d.reason, "at": d.at} for d in ledger_history(base, gate)],
            **extra}


def ledger_history(base: dict, gate: Gate) -> list:
    return base["_ledger"].history(gate)


def _reply(ws: Workspace, base: dict, gate: Gate, dg: str) -> tuple[bool, dict | None]:
    """(هل تُعرض البطاقة، جواب الخط إن وُجد). قرار سُجّل على هذه البصمة يخفي البطاقة، إلا طلب تعديل أجابه النموذج ولم يغيّر
    المعروض: تعود البطاقة بجوابه بدل أن يعلق الإصدار، وقرار المالك التالي على البصمة نفسها يسري."""
    dec = base["_ledger"].latest(gate, dg)
    if dec is None:
        return True, None
    text = revise_reply(ws, dec, gate)
    return text is not None, ({"note": dec.reason, "text": text} if text is not None else None)


def _strategy_gate(ws: Workspace, v: Path, base: dict, rel: str) -> dict | None:
    """بلا شرط على علامة `strategy`: منصة عُدّلت بعد اعتمادها بصمتها جديدة بلا قرار، والخط ينتظر المالك عندها (كانت العلامة
    الباقية تخفي بطاقتها)."""
    s, problems = read_strategy(ws)
    if s is None or problems:
        return None
    dg = digest([strategy_path(ws)])
    show, reply = _reply(ws, base, Gate.STRATEGY, dg)
    if not show:
        return None
    vis = _visuals(ws, rel)
    return _gate(base, Gate.STRATEGY, dg, visuals=vis, directions_digest=directions_digest(ws) if vis["options"] else "", reply=reply, strategy={
        "positioning": s.positioning, "promise": s.promise, "tagline": s.tagline,
        "personality": [{"trait": t.trait, "means": t.means, "not": t.not_} for t in s.personality],
        "voice_do": list(s.voice_do), "voice_dont": list(s.voice_dont), "samples": dict(s.samples), "imagery": s.imagery})


def _options(ws: Workspace, rel: str) -> list[dict]:
    dirs, _ = read_directions(ws)
    return [{"id": d.id, "name": d.name, "idea": d.idea, "swatches": [d.colors[k] for k in ("brand", "accent", "paper", "ink")],
             "img": f"{rel}/identity-board/{d.id}-social-post.svg", "slide": f"{rel}/identity-board/{d.id}-slide-title.svg"}
            for d in dirs if (ws.root / "identity-board" / f"{d.id}-social-post.svg").is_file()]


def _visuals(ws: Workspace, rel: str) -> dict:
    """ما يُرى بالعين بجانب أي بوابة هوية: العلامة المعتمدة، وورقة المعاينة، ولوحة الاتجاهات إن بُنيت للمحتوى الحالي."""
    approved = Ledger(ws.ledger_path).approved()
    mark = f"{rel}/work/concepts/{approved.concept_id}.svg" if approved and (ws.concepts_dir / f"{approved.concept_id}.svg").is_file() else ""
    fresh = (ws.root / "directions.html").is_file() and ws.read_marker("directions_board").get("digest") == directions_digest(ws)
    final = ws.package_dir / "identity" / "reveal.html"
    reveal = f"{rel}/package/identity/reveal.html" if final.is_file() else (f"{rel}/reveal.html" if fresh and (ws.root / "reveal.html").is_file() else "")
    return {"mark": mark, "reveal": reveal, "preview": f"{rel}/preview.html" if (ws.root / "preview.html").is_file() else "",
            "board": f"{rel}/directions.html" if fresh else "", "options": _options(ws, rel) if fresh else []}


def _directions_gate(ws: Workspace, v: Path, base: dict, rel: str) -> dict | None:
    """بلا شرط على علامة `directions`: القرار على البصمة هو ما يخفي البطاقة. علامة موروثة ببصمة مطابقة كانت تخفيها والقرار
    لم يورَّث، فيقف الخط عند المالك بلا بطاقة."""
    if not (ws.root / "directions.html").is_file():
        return None
    dg = directions_digest(ws)
    if ws.read_marker("directions_board").get("digest") != dg:
        return None
    show, reply = _reply(ws, base, Gate.DIRECTIONS, dg)
    if not show:
        return None
    return _gate(base, Gate.DIRECTIONS, dg, board=f"{rel}/directions.html", options=_options(ws, rel), visuals=_visuals(ws, rel),
                 reply=reply)


def _book_gate(ws: Workspace, v: Path, base: dict, rel: str) -> dict | None:
    book = ws.package_dir / "identity" / "brand-book.html"
    if not book.is_file() or ws.done("identity"):
        return None
    dg = digest([book])
    show, reply = _reply(ws, base, Gate.BOOK, dg)
    if not show:
        return None
    pdf = book.with_suffix(".pdf")
    apps = [f"{rel}/package/identity/applications/{a}.svg" for a in ("social-post", "slide-title", "letterhead", "card-front", "social-cover",
                                                                       "app-splash") if (book.parent / "applications" / f"{a}.svg").is_file()]
    sketch = 0  # مسار المصمّم الخارجي: الرمز مبني من سكتش اختاره المالك، وله أن يردّه إلى المصمّم إن لم يطابقه
    if designer.frozen_enabled(ws.root):
        sheet, _ = designer.read_sheet(ws)
        choice = designer.current(ws, sheet) if sheet is not None else None
        sketch = int(choice["sketch"]) if choice is not None else 0
    return _gate(base, Gate.BOOK, dg, visuals=_visuals(ws, rel), apps=apps, book=f"{rel}/package/identity/brand-book.html",
                 pdf=f"{rel}/package/identity/brand-book.pdf" if pdf.is_file() else "", designer_sketch=sketch, reply=reply)


# بطاقة كل بوابة باسمها في نتيجة الخط (Outcome.gate)
GATE_CARDS = {"style": _style_gate, "sketches": _sketch_gate, "concepts": _concepts_gate, "name_check": _name_gate,
              Gate.STRATEGY.value: _strategy_gate, Gate.DIRECTIONS.value: _directions_gate, Gate.BOOK.value: _book_gate}


def _after(item: dict, identity: bool) -> tuple[str, str]:
    """عنوان ما ينتظر المالك، وما سيحدث بعد ضغطته بالضبط: أين يمضي الخط ومتى يعود إليه."""
    kind, gate = item["kind"], item.get("gate")
    if kind == "stalled":
        return "الخط واقف عندك", ("وقف الخط عند ما لا قرار له في بطاقة، أو تغيّر المعروض بعد وقوفه. اقرأ ما وقف عنده، وأصلِح ما يذكره إن "
                                  "ذكر شيئًا، ثم استأنف الخط من الزر؛ يعود إليك ببطاقة القرار أو يمضي.")
    rest = "ثم يكتب النموذج المنصة الاستراتيجية ويعود إليك لاعتمادها مع الاتجاه" if identity else "ثم تُبنى الحزمة ويُغلق الإصدار"
    if kind == "style":
        return "اختيار الطابع البصري", ("اختر أسلوبًا أو اثنين يمثلان «الحديث والمبتكر» عندك، وأضف ملاحظة إن شئت. بعدها يرسم النموذج "
                                       "المفاهيم الخمسة بهذا الطابع وحده، ويحكم عليها الحَكَم بالتزامها به، ثم تعود إليك لاختيار المفهوم.")
    if kind == "sketches":
        return "اختيار السكتش", ("اختر سكتشًا واحدًا برقمه، وأضف ملاحظة إن شئت. اختيارك أمرٌ بإرسال السكتش إلى المصمّم الخارجي ليبنيه "
                                 "متجهًا كما هو، ثم تفحصه سِمة وتبني الهوية كاملة وتعود إليك بالدليل وحده، وهو قرارك الأخير. "
                                 "ويبقى عليك قبل الحزمة تحققك من توافر الاسم.")
    if kind == "concepts":
        return "اختيار المفهوم", (f"بعد الاعتماد: تتحقق من توافر الاسم بنفسك، {rest}. الرفض أو التعديل يعيد رسم ذلك المفهوم بسببك "
                                  "في الوسيط نفسه، ثم يحكم عليه الحَكَم المستقل قبل أن يعود إليك. الوسيط لا يتغيّر إلا باختيارك.")
    if kind == "name_check":
        return "تحقق توافر الاسم", f"بعد التسجيل بـ«متاح»: تُبنى حزمة العلامة، {rest}. «متعارض» يوقف الخط حتى اسم جديد."
    if gate == "strategy" and not (item.get("visuals") or {}).get("options"):
        # مشروع جديد بلا علامة بعد: لا اتجاهات للاختيار هنا، والخط يمضي إلى المفاهيم
        return ("اعتماد المنصة الاستراتيجية",
                "بعد الاعتماد: يرسم النموذج آليًا خمسة مفاهيم متباعدة ويفحصها الخط وينقدها، ثم يعود إليك لاختيار المفهوم. "
                "التعديل أو الرفض يعيد المنصة إلى النموذج بسببك.")
    if gate == "strategy":
        return ("اعتماد المنصة الاستراتيجية واختيار الاتجاه",
                "إن اخترت اتجاهًا مع الاعتماد: يبني الخط الهوية كاملة بلا توقف ويعود إليك بالدليل وحده، وهو آخر قرار. "
                "بلا اختيار: يتوقف الخط عند بوابة الاتجاهات.")
    if gate == "directions":
        return "اختيار اتجاه الهوية", "بعد الاعتماد: يبني الخط الهوية كاملة (الألوان والخطوط والأيقونات والتطبيقات والدليل) ويعود إليك بالدليل، وهو آخر قرار."
    return "اعتماد دليل الهوية", "بعد الاعتماد: يُغلق الإصدار وتُحفظ الهوية بأصولها في قاعدة سِمة، ويصير جاهزًا للتسليم. لا قرار بعده."


def owner_inbox(out_dir: Path) -> list[dict]:
    if not out_dir.is_dir():
        return []
    out = []
    for p in sorted(out_dir.iterdir()):
        if not p.is_dir() or p.name.startswith("_"):  # مجلدات الأدوات المؤقتة ليست مشاريع
            continue
        try:
            i = _guarded_item(out_dir, p)
        except READ_ERRORS as e:
            i = _unreadable(p, e)
        if i:
            out.append(i)
    return out


# ما يرميه ملف معطوب أو في منتصف كتابته (run.json نصف مكتوب، concepts.yaml لا تُقرأ صيغته، علامة مرحلة مبتورة)
READ_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError)


def _guarded_item(out_dir: Path, project_dir: Path) -> dict | None:
    i = _item(out_dir, project_dir)
    if i:
        i.pop("_ledger", None)
        brief = out_dir / i["project"] / f"v{i['version']}" / "brief.json"
        identity = bool(json.loads(brief.read_text(encoding="utf-8")).get("identity")) if brief.is_file() else False
        i["title"], i["after"] = _after(i, identity)
    return i


def _unreadable(project_dir: Path, error: Exception) -> dict:
    """بند المشروع الذي تعذّرت قراءة ملفاته: ملف واحد معطوب في مشروع واحد كان يُسقط `/api/state` وكل `/api/timeline/*`
    فتظهر المنصة كلها «منقطع». الآن يظهر في مكانه بطاقة «الخط واقف عندك» بسبب العطل، وبقية المشاريع كما هي."""
    versions = _versions(project_dir)
    n = versions[-1][0] if versions else 0
    msg = (f"تعذّرت قراءة ملفات الإصدار v{n} ({type(error).__name__}: {str(error)[:300]}). قد يكون ملف في منتصف كتابته: إن بقيت "
           "البطاقة فاستأنف الخط ليعيد كتابة ما يملكه، أو صحّح الملف المذكور.")
    return {"project": project_dir.name, "version": n, "key": "", "brief": "", "preview": "", "kind": "stalled", "digest": "",
            "message": msg, "problem": True, "title": "ملفات الإصدار لا تُقرأ",
            "after": "إن كان الملف في منتصف كتابته عادت بطاقة المشروع من تلقاء نفسها؛ وإن بقي معطوبًا فاستئناف الخط يعيد كتابة ما يملكه."}


def mentioned_ids(reason: str, ids: set[str]) -> list[str]:
    """معرّفات الخيارات المذكورة نصًا في ملاحظة المالك (d2، w1، c3...)، كلمةً مستقلة لا جزءًا من كلمة."""
    return sorted(i for i in ids if i and re.search(rf"(?<![A-Za-z0-9]){re.escape(i)}(?![A-Za-z0-9])", reason, re.IGNORECASE))


def guard_intent(reason: str, ids: set[str], chosen: str) -> None:
    """حارس نية القرار: الاختيار لا يُستنتج من نص الملاحظة. إن ذُكر في ملاحظة الاعتماد خيار غير المختار يُوقف القرار
    ويُطلب الاختيار صراحة، فلا يضيع ما قصده المالك ولا يُعتمد ما لم يختره."""
    other = [i for i in mentioned_ids(reason, ids) if i.lower() != chosen.lower()]
    if other:
        raise InboxError(f"ذكرتَ {'، '.join(other)} في الملاحظة ولم تختره. اختره من الخيارات المعروضة، "
                         "أو احذفه من الملاحظة إن لم تقصد اختياره.")


def _current(out_dir: Path, project: str, version: int, key: str, kind: str) -> dict:
    item = _item(out_dir, out_dir / project) if (out_dir / project).is_dir() and "/" not in project and ".." not in project else None
    if item is None or item["version"] != version or item["key"] != key:
        raise InboxError("تغيّر ما عُرض عليك منذ فتح الصفحة؛ حدّثها ثم قرّر من جديد.")
    if item["kind"] != kind:
        raise InboxError("هذا المشروع لم يعد ينتظر هذا القرار؛ حدّث الصفحة.")
    return item


def decide(out_dir: Path, project: str, version: int, key: str, verdict: str, concept_id: str, reason: str,
           digest_: str | None = None) -> str:
    """قرار في مفهوم معروض: اعتماد، أو تعديل بسبب، أو رفض بسبب. الرفض بسبب يعيد رسم المفهوم في الوسيط نفسه.
    digest_: بصمة ما رآه المالك؛ من المنصة إلزامية، فلا تعتمد صفحة قديمة رسمًا عدّله النموذج بعد عرضه."""
    item = _current(out_dir, project, version, key, "concepts")
    if digest_ is not None and digest_ != item["digest"]:
        raise InboxError("تغيّرت رسوم المفاهيم منذ فتح الصفحة؛ حدّثها وانظر الرسوم الجديدة ثم قرّر.")
    try:
        v = Verdict(verdict)
    except ValueError as e:
        raise InboxError("قرار غير معروف.") from e
    if concept_id not in {c["id"] for c in item["concepts"]}:
        raise InboxError("المفهوم ليس من المعروض.")
    reason = _within(reason.strip(), "decide")
    if v is Verdict.APPROVED:
        guard_intent(reason, {c["id"] for c in item["concepts"]}, concept_id)
    if v is not Verdict.APPROVED and len(reason) < MIN_REASON:
        raise InboxError("الرفض وطلب التعديل يحتاجان سببًا يفهمه النموذج في الجولة التالية.")
    ws, _ = _workspace(out_dir / project / f"v{version}")
    record_decision(ws, concept_id, v, reason or "اعتماد من منصة سِمة")
    return f"{VERDICT_AR[v]} {concept_id} في {project} v{version}."


def switch_medium(out_dir: Path, project: str, version: int, key: str, medium: str, reason: str,
                  digest_: str | None = None) -> str:
    """المالك يختار الوسيط، أو يطلب رسمًا جديدًا كاملًا في الوسيط الحالي بالمعيار. يحتاج سببًا يقرؤه الرسّام.
    digest_: بصمة ما رآه المالك؛ من المنصة إلزامية كقرار المفهوم، فلا يُطلب رسم جديد عن رسوم تغيّرت بعد عرضها (م5)."""
    item = _current(out_dir, project, version, key, "concepts")
    if digest_ is not None and digest_ != item["digest"]:
        raise InboxError("تغيّرت رسوم المفاهيم منذ فتح الصفحة؛ حدّثها وانظر الرسوم الجديدة ثم قرّر.")
    if medium not in MEDIUM_AR:
        raise InboxError("وسيط غير معروف.")
    reason = _within(reason.strip(), "medium")
    if len(reason) < MIN_REASON:
        raise InboxError("اكتب ما تريده من الرسم الجديد؛ يقرؤه الرسّام والحَكَم.")
    ws, _ = _workspace(out_dir / project / f"v{item['version']}")
    record_switch(ws, Medium(medium), reason)
    same = medium == item.get("medium")
    return (f"رسم جديد كامل بوسيط «{MEDIUM_AR[medium]}» في {project} v{version}" + (" (الوسيط نفسه)" if same else "")
            + "؛ يعود إليك بعد التحكيم.")


def choose_style(out_dir: Path, project: str, version: int, key: str, digest_: str, picked: list[str], note: str) -> str:
    """اختيار المالك للطابع من العينات المعروضة نفسها (بصمتها)، ثم يُرسم كل شيء بعده بهذا الطابع."""
    item = _current(out_dir, project, version, key, "style")
    if digest_ != item["digest"]:
        raise InboxError("تغيّرت العينات منذ فتح الصفحة؛ حدّثها ثم اختر من جديد.")
    ws, _ = _workspace(out_dir / project / f"v{version}")
    try:
        row = style.record(ws, picked, _within(note, "note"), digest_)
    except ValueError as e:
        raise InboxError(str(e)) from e
    names = "، ".join(style.catalog()[s][0] for s in row["styles"])
    return f"اختير الطابع «{names}» في {project} v{version}؛ يرسم الرسّام المفاهيم به ثم يحكم الحَكَم."


def choose_sketch(out_dir: Path, project: str, version: int, key: str, digest_: str, sketch: int, note: str) -> str:
    """اختيار المالك سكتشًا من الصفحة المعروضة نفسها (بصمتها)؛ يُبنى بعده متجهًا عند المصمّم الخارجي."""
    _current(out_dir, project, version, key, "sketches")
    ws, _ = _workspace(out_dir / project / f"v{version}")
    sheet, _ = designer.read_sheet(ws)
    try:
        if sheet is None:
            raise designer.DesignerError("صفحة السكتشات لم تعد صالحة؛ حدّث الصفحة.")
        designer.record(ws, sheet, sketch, _within(note, "note"), digest_)
    except designer.DesignerError as e:
        raise InboxError(str(e)) from e
    return f"اختير السكتش {sketch} في {project} v{version}؛ يُرسل إلى المصمّم الخارجي ليبنيه متجهًا ثم تفحصه سِمة."


def develop_sketch(out_dir: Path, project: str, version: int, key: str, digest_: str, sketch: int, note: str) -> str:
    """«طوّر هذا السكتش»: المالك اختار سكتشًا من الصفحة المعروضة (بصمتها) ويريد صفحة معالجات حوله قبل بنائه متجهًا."""
    _current(out_dir, project, version, key, "sketches")
    ws, _ = _workspace(out_dir / project / f"v{version}")
    sheet, _ = designer.read_sheet(ws)
    try:
        if sheet is None:
            raise designer.DesignerError("صفحة السكتشات لم تعد صالحة؛ حدّث الصفحة.")
        designer.develop(ws, sheet, sketch, _within(note, "note"), digest_)
    except designer.DesignerError as e:
        raise InboxError(str(e)) from e
    return f"طُلب تطوير السكتش {sketch} في {project} v{version}؛ يعود إلى المصمّم الخارجي ليرسم صفحة معالجات حوله ثم تختار منها."


def reject_sketches(out_dir: Path, project: str, version: int, key: str, digest_: str, reason: str) -> str:
    """رفض المالك صفحة السكتشات المعروضة نفسها (بصمتها) بسبب؛ تعود إلى المصمّم الخارجي بسببه ليرسم صفحة جديدة."""
    _current(out_dir, project, version, key, "sketches")
    ws, _ = _workspace(out_dir / project / f"v{version}")
    sheet, _ = designer.read_sheet(ws)
    try:
        if sheet is None:
            raise designer.DesignerError("صفحة السكتشات لم تعد صالحة؛ حدّث الصفحة.")
        designer.reject(ws, sheet, _within(reason, "reason"), digest_)
    except designer.DesignerError as e:
        raise InboxError(str(e)) from e
    return f"رُفضت صفحة السكتشات في {project} v{version}؛ يُكتب طلب صفحة جديدة بسببك ويُرسل إلى المصمّم الخارجي."


def return_vector(out_dir: Path, project: str, version: int, key: str, digest_: str, reason: str) -> str:
    """ردّ المالك المتجه المبني من بطاقة الدليل المعروضة نفسها (بصمتها): الشعار لا يطابق السكتش الذي اختاره، فيعود السكتش
    نفسه إلى المصمّم الخارجي بسببه بنصّه. ليس «تعديل الدليل»: ذاك يذهب إلى نموذج الخط الذي لا يملك الشعار."""
    try:
        item = _current(out_dir, project, version, key, "identity")
        shown = item["gate"] == Gate.BOOK.value and bool(item.get("designer_sketch"))
    except InboxError:
        # أو من وقوف الخط عنده بعد استنفاد جولات التصحيح (ب4): لا دليل بعد، وردّه يعيد السكتش إلى المصمّم ببناء جديد
        item = _current(out_dir, project, version, key, "stalled")
        o = outcome.current(out_dir / project / f"v{version}")
        shown = o is not None and o["gate"] == designer.FIX_GATE
    if not shown or item["digest"] != digest_:
        raise InboxError("تغيّر ما عُرض عليك منذ فتح الصفحة؛ حدّثها ثم قرّر من جديد.")
    ws, _ = _workspace(out_dir / project / f"v{version}")
    sheet, _ = designer.read_sheet(ws)
    try:
        if sheet is None:
            raise designer.DesignerError("صفحة السكتشات لم تعد صالحة؛ حدّث الصفحة.")
        row = designer.rebuild(ws, sheet, _within(reason, "reason"))
    except designer.DesignerError as e:
        raise InboxError(str(e)) from e
    return f"رُدّ متجه السكتش {row['sketch']} في {project} v{version}؛ يُكتب طلب إعادة بنائه بسببك ويُرسل إلى المصمّم الخارجي."


def name_check(out_dir: Path, root: Path, project: str, version: int, key: str, status: str, sources: list[str], note: str) -> str:
    """نتيجة تحقق المالك اليدوي من توافر الاسم. «متاح» يحتاج مصدرًا رسميًا واحدًا على الأقل؛ والأداة لا تستعلم الشبكة."""
    item = _current(out_dir, project, version, key, "name_check")
    try:
        st = NameStatus(status)
    except ValueError as e:
        raise InboxError("حالة غير معروفة.") from e
    problem = result_problem(st, sources, _within(note, "note"))
    if problem:
        raise InboxError(problem)
    ws, _ = _workspace(out_dir / project / f"v{version}")
    brief = load_brief(root / item["brief"])
    nc = record_name_check(ws, brief, st, sources, note.strip())
    return f"سُجّل تحقق الاسم «{nc.name}» في {project} v{version}."


def identity_decide(out_dir: Path, project: str, version: int, key: str, gate: str, digest_: str, verdict: str, option: str,
                    reason: str, option_digest: str = "") -> str:
    """قرار المالك في بوابة هوية مربوط بـhash ما عُرض: المنصة الاستراتيجية، أو الاتجاه، أو الدليل.

    اعتماد المنصة مع اختيار اتجاه من لوحة الاطلاع (option + option_digest) يسجّل القرارين معًا، بشرط أن تكون
    الاتجاهات المعروضة هي الحالية نفسها؛ فيمضي الخط حتى الدليل دون توقف ثانٍ."""
    item = _current(out_dir, project, version, key, "identity")
    if item["gate"] != gate or item["digest"] != digest_:
        raise InboxError("تغيّر ما عُرض عليك منذ فتح الصفحة؛ حدّثها ثم قرّر من جديد.")
    try:
        v = Verdict(verdict)
    except ValueError as e:
        raise InboxError("قرار غير معروف.") from e
    reason = _within(reason.strip(), "identity")
    if v is not Verdict.APPROVED and len(reason) < MIN_REASON:
        raise InboxError("الرفض وطلب التعديل يحتاجان سببًا يفهمه النموذج في الجولة التالية.")
    g = Gate(gate)
    if v is Verdict.APPROVED:
        shown = item.get("options") if g is Gate.DIRECTIONS else item.get("visuals", {}).get("options", [])
        guard_intent(reason, {o["id"] for o in shown or []}, option)
    if g is Gate.DIRECTIONS and v is Verdict.APPROVED and option not in {o["id"] for o in item["options"]}:
        raise InboxError("اختر اتجاهًا من الثلاثة المعروضة.")
    combo = g is Gate.STRATEGY and v is Verdict.APPROVED and bool(option)
    if combo:
        shown = {o["id"] for o in item.get("visuals", {}).get("options", [])}
        if option not in shown or not option_digest or option_digest != item.get("directions_digest"):
            raise InboxError("تغيّرت الاتجاهات المعروضة منذ فتح الصفحة؛ حدّثها ثم اختر من جديد.")
    ws, _ = _workspace(out_dir / project / f"v{version}")
    led = id_ledger(ws)
    led.record(g, digest_, v.value, option if g is Gate.DIRECTIONS else "", reason or "اعتماد من منصة سِمة")
    if combo:
        led.record(Gate.DIRECTIONS, option_digest, Verdict.APPROVED.value, option, "اختير مع اعتماد المنصة الاستراتيجية")
        return f"{VERDICT_AR[v]}: {GATE_AR[g]} واختيار الاتجاه {option} في {project} v{version}."
    return f"{VERDICT_AR[v]}: {GATE_AR[g]} في {project} v{version}."


def resume(out_dir: Path, project: str, version: int, key: str) -> str:
    """استئناف الخط بطلب المالك على الإصدار المعروض نفسه: آخر إصدار للمشروع، مفتوحًا، بالمفتاح الذي رآه. لا يسجّل قرارًا؛
    يعيد تشغيل `sima run` حيث وقف (توقف التشغيل الآلي، أو قرار سُجّل ولم يُستأنف، أو خطأ أُصلح)."""
    if not project or any(x in project for x in ("/", "\\", "..")) or not (out_dir / project).is_dir():
        raise InboxError("مشروع غير معروف.")
    versions = _versions(out_dir / project)
    if not versions or versions[-1][0] != version or not (versions[-1][1] / "run.json").is_file():
        raise InboxError("تغيّر ما عُرض عليك منذ فتح الصفحة؛ حدّثها ثم استأنف.")
    ws, run = _workspace(versions[-1][1])
    if ws.key.key != key:
        raise InboxError("تغيّر ما عُرض عليك منذ فتح الصفحة؛ حدّثها ثم استأنف.")
    if run.get("closed"):
        raise InboxError("هذا الإصدار مكتمل؛ لا خط يُستأنف عليه.")
    return f"يُستأنف الخط على {project} v{version}."


def brief_path(out_dir: Path, root: Path, project: str, version: int) -> Path:
    _, run = _workspace(out_dir / project / f"v{version}")
    return root / str(run.get("brief_source", ""))


def brief_unchanged(out_dir: Path, root: Path, project: str, version: int) -> None:
    """قرار على vN لا يُقبل إن عُدّل موجزه بعد فتحه (مراجعة 2026-11-14، م2): الاستئناف يشغّل `sima run` على الموجز الحي،
    فيفتح مفتاحه الجديد إصدارًا آخر ويبقى القرار على إصدار لا يكمله أحد (هكذا صار v5 من «أوراق» v6). يُنادى قبل تسجيل أي
    قرار أو استلام يستأنف الخط. ما لا يُقارن (مشروع أو إصدار غير صالح، موجز غير موجود) يُترك لحراسة القرار نفسه."""
    v = out_dir / project / f"v{version}"
    if not project or any(x in project for x in ("/", "\\", "..")) or not (v / "run.json").is_file():
        return
    ws, run = _workspace(v)
    src = root / str(run.get("brief_source") or "")
    if not src.is_file():
        return
    try:
        live = load_brief(src)
    except Exception as e:  # موجز لا يُقرأ لا يُستأنف عليه خط
        raise InboxError(f"تعذّرت قراءة موجز المشروع ({type(e).__name__}): أصلِحه ثم قرّر من جديد.") from e
    if live.project != ws.key.project or live.hash() != ws.key.brief_hash:
        raise InboxError(f"عُدّل موجز المشروع بعد فتح v{version}: قرارك هنا لن يستأنف الخط على هذا الإصدار. أعد الموجز كما كان "
                         f"ثم قرّر، أو شغّل `sima run` ليُفتح الإصدار الجديد بالموجز المعدَّل وقرّر عليه.")


def renew_reason(out_dir: Path, root: Path, project: str, version: int) -> str:
    """لماذا يُفتح إصدار جديد بعد vN، أو "" إن لم يلزم (قرار المالك 2026-11-20: زر «إصدار جديد» في المنصة بدل `sima run
    --new-version` من الطرفية). يلزم حين يكون vN آخر إصدار للمشروع ومغلقًا وتغيّر بعده ما يدخل الخط: موجزه، أو محتوى بيان
    الاعتماد (البصمة لا الملف، فتعليق فيه لا يطلب إصدارًا). البيان لا يُقرأ إلا بعد التحقق، فخطؤه سبب يُعرض لا زر."""
    if not project or any(x in project for x in ("/", "\\", "..")):
        return ""
    v = out_dir / project / f"v{version}"
    versions = _versions(out_dir / project)
    if not versions or versions[-1][0] != version or not (v / "run.json").is_file():
        return ""
    try:
        ws, run = _workspace(v)
    except (KeyError, ValueError):  # run.json ناقص (إصدار قديم أو مكتوب يدويًا): لا زر
        return ""
    src = root / str(run.get("brief_source") or "")
    if not run.get("closed") or not src.is_file():
        return ""
    try:
        live = load_brief(src)
        adoption = adopt.load(live)
    except Exception:  # noqa: BLE001 — موجز أو بيان لا يُقرأ يُصلَح أولًا؛ `sima run` يذكر سببه
        return ""
    if live.hash() != ws.key.brief_hash:
        return f"عُدّل موجز المشروع بعد إغلاق v{version}."
    if adoption is not None and ws.read_marker(adopt.MARKER).get("digest") not in (None, adoption.digest):
        return f"تغيّر محتوى بيان الاعتماد بعد إغلاق v{version}."
    return ""


def renew(out_dir: Path, root: Path, project: str, version: int, key: str) -> str:
    """فتح إصدار جديد بطلب المالك بعد الإصدار المعروض: آخر إصدار، بالمفتاح الذي رآه، مغلقًا، وتغيّر بعده ما يدخل الخط."""
    if not project or any(x in project for x in ("/", "\\", "..")) or not (out_dir / project).is_dir():
        raise InboxError("مشروع غير معروف.")
    versions = _versions(out_dir / project)
    if not versions or versions[-1][0] != version or not (versions[-1][1] / "run.json").is_file():
        raise InboxError("تغيّر ما عُرض عليك منذ فتح الصفحة؛ حدّثها ثم أعد المحاولة.")
    ws, run = _workspace(versions[-1][1])
    if ws.key.key != key:
        raise InboxError("تغيّر ما عُرض عليك منذ فتح الصفحة؛ حدّثها ثم أعد المحاولة.")
    if not run.get("closed"):
        raise InboxError(f"v{version} مفتوح بعد؛ يُستأنف ولا يُفتح بعده إصدار.")
    why = renew_reason(out_dir, root, project, version)
    if not why:
        raise InboxError(f"لم يتغيّر ما يدخل الخط بعد v{version}؛ لا إصدار جديد بلا مدخل جديد.")
    return f"{why} يُفتح v{version + 1} في الخلفية."


def resume_args(out_dir: Path, project: str, version: int) -> dict:
    """ما يُمرَّر إلى `sima run` عند الاستئناف من المنصة: بذرة الإصدار (قد تخالف بذرة الموجز إن فُتح بـ`--seed`) ومفتاحه
    المتوقع، فيخرج الأمر بخطأ إن لم يطابقه الموجز بدل أن يفتح إصدارًا آخر."""
    ws, _ = _workspace(out_dir / project / f"v{version}")
    return {"seed": ws.key.seed, "expect_key": ws.key.key}
