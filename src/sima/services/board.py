"""لوحة الأتمتة الحية: لقطة حالة حتمية من دفتر بطاقات المشغّل ومراحل سِمة، بلا آثار جانبية.

المحوّل (adapters/board_server.py) يخدمها JSON والصفحة تستطلعها كل بضع ثوانٍ.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import config

CARD_FLOW = ("created", "ready", "claimed", "coded", "prepush_ok", "pr_opened", "ci_green", "preview_ready", "approved", "merged", "deployed")
CARD_FAIL = {"prepush_failed": "coded", "blocked": None, "cancelled": None}
CARD_AR = {
    "created": "أُنشئت", "ready": "جاهزة", "claimed": "التُقطت", "coded": "كُتبت", "prepush_ok": "الفحص المحلي نجح",
    "prepush_failed": "الفحص المحلي فشل", "pr_opened": "طلب الدمج مفتوح", "ci_green": "CI أخضر", "approved": "اعتمدها المالك",
    "merged": "دُمجت", "deployed": "نُشرت", "blocked": "متوقفة", "cancelled": "أُلغيت",
    "preview_ready": "جاهزة للمعاينة", "preview_rejected": "رفض المالك المعاينة",
}


def _read_jsonl(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def card_steps(events: list[dict]) -> list[dict]:
    """خطوات البطاقة: done / failed / current / pending، مع آخر وقت لكل خطوة منجزة."""
    seen = {e.get("event"): e.get("at", "") for e in events}
    last = events[-1].get("event") if events else None
    steps = []
    reached = {e.get("event") for e in events}
    for name in CARD_FLOW:
        status = "done" if name in reached else "pending"
        steps.append({"key": name, "label": CARD_AR[name], "status": status, "at": seen.get(name, "")})
    if last == "prepush_failed":
        idx = CARD_FLOW.index("prepush_ok")
        steps[idx] = {"key": "prepush_failed", "label": CARD_AR["prepush_failed"], "status": "failed", "at": seen.get(last, "")}
    elif last in ("blocked", "cancelled"):
        steps.append({"key": last, "label": CARD_AR[last], "status": "failed", "at": seen.get(last, "")})
    else:
        nxt = next((s for s in steps if s["status"] == "pending"), None)
        if nxt is not None and last != "deployed":
            nxt["status"] = "current"
    return steps


# رحلة البطاقة في ست عقد (على نمط صفحة «المشغّل الحي» في ميزان): كل عقدة يُدخَل إليها بأحد أحداثها،
# والعقدة الأخيرة المدخولة هي الجارية وما قبلها منجز
TRACK = (
    ("queue", "في الطابور", ("created", "ready")),
    ("model", "النموذج يكتب", ("claimed",)),
    ("verify", "الفحص المحلي", ("coded", "prepush_ok", "prepush_failed")),
    ("pr", "طلب الدمج وCI", ("pr_opened", "ci_green")),
    ("preview", "المعاينة", ("preview_ready",)),
    ("approve", "اعتماد المالك", ("approved", "preview_rejected")),
    ("merge", "الدمج", ("merged",)),
    ("published", "منشورة وسليمة", ("deployed",)),
)
STATUS_AR = {
    "created": "أُنشئت البطاقة وتنتظر وضعها جاهزة.",
    "ready": "في الطابور؛ يلتقطها المشغّل في دورته القادمة.",
    "claimed": "التقطها المشغّل؛ النموذج يكتب في worktree.",
    "coded": "أودع النموذج تغييره؛ الفحص المحلي جارٍ.",
    "prepush_ok": "نجح الفحص المحلي؛ الدفع وفتح طلب الدمج.",
    "prepush_failed": "فشل الفحص المحلي؛ البطاقة باقية في worktree للمراجعة.",
    "pr_opened": "فُتح طلب الدمج؛ فحوص CI جارية، والمعاينة تُجهَّز.",
    "ci_green": "CI أخضر؛ تُجهَّز المعاينة على منفذ محلي.",
    "preview_ready": "جاهزة للمعاينة؛ تنتظر قرارك مربوطًا بالرأس المعروض.",
    "approved": "اعتمدها المالك؛ سطر الاعتماد في الوصف ثم الدمج بعد CI والبوابة.",
    "preview_rejected": "رفض المالك المعاينة؛ يُغلق الطلب بالسبب.",
    "merged": "دُمجت؛ ينتظر ظهور commit الدمج في فحص صحة الإنتاج.",
    "deployed": "نُشرت وفحص الصحة سليم.",
    "blocked": "متوقفة؛ تحتاج تدخّل المالك.",
    "cancelled": "أُلغيت.",
}
LOG_KIND = {"prepush_failed": "bad", "preview_rejected": "bad", "blocked": "bad", "cancelled": "bad", "deployed": "good", "merged": "good", "approved": "good"}


def _attempt(events: list[dict]) -> list[dict]:
    """أحداث المحاولة الحالية: من آخر «ready» (إعادة التشغيل تبدأ محاولة جديدة)."""
    idx = max((i for i, e in enumerate(events) if e.get("event") == "ready"), default=0)
    return events[idx:]


def card_track(events: list[dict]) -> dict:
    """عقد الرحلة الثماني، وموضع الشارة p (0..7)، وحالتها، وسطر الحالة."""
    cur = _attempt(events)
    seen: dict[str, str] = {}
    for e in cur:
        seen[str(e.get("event"))] = str(e.get("at", ""))
    if events and "created" not in seen:
        seen["created"] = str(events[0].get("at", ""))
    last = str(events[-1].get("event")) if events else ""
    reached = 0
    for i, (_, _, evs) in enumerate(TRACK):
        if any(ev in seen for ev in evs):
            reached = i
    failed = last in ("prepush_failed", "preview_rejected", "blocked", "cancelled")
    finished = last == "deployed"
    nodes = []
    for i, (key, label, evs) in enumerate(TRACK):
        at = next((seen[ev] for ev in evs if ev in seen), "")
        if i < reached or (finished and i == reached):
            st = "done"
        elif i == reached:
            st = "fail" if failed else "active"
        else:
            st = "pending"
        nodes.append({"key": key, "label": label, "status": st, "at": at})
    chip = "good" if finished else ("bad" if failed else "run")
    return {"nodes": nodes, "p": reached, "chip": chip, "status": STATUS_AR.get(last, last),
            "status_kind": "bad" if failed else ("good" if finished else ""),
            "attempt_start": str(cur[0].get("at", "")) if cur else "", "stage_since": nodes[reached]["at"],
            "attempts": max(1, sum(1 for e in events if e.get("event") == "claimed"))}


def card_log(events: list[dict]) -> list[dict]:
    out = []
    for e in reversed(events):
        ev = str(e.get("event"))
        text = CARD_AR.get(ev, ev)
        extra = e.get("note") or (f"الرأس {str(e['head'])[:8]}" if e.get("head") else "") or e.get("url") or ""
        if ev == "coded" and e.get("exit_code") not in (None, 0):
            extra = f"رمز الخروج {e['exit_code']}"
        out.append({"at": str(e.get("at", "")), "text": text + (f": {extra}" if extra else ""), "kind": LOG_KIND.get(ev, "")})
    return out


def ledger_state(repo: Path) -> list[dict]:
    ledger = repo / "automation" / "ledger"
    if not ledger.is_dir():
        return []
    cards = []
    for p in sorted(ledger.glob("*.jsonl")):
        evs = _read_jsonl(p)
        if not evs:
            continue
        first, last = evs[0], evs[-1]
        cards.append({
            "id": p.stem, "title": first.get("title", p.stem), "state": last.get("event"),
            "state_ar": CARD_AR.get(str(last.get("event")), str(last.get("event"))), "updated": last.get("at", ""),
            "created": first.get("at", ""),
            "url": next((e.get("url") for e in reversed(evs) if e.get("url")), ""), "steps": card_steps(evs),
            "track": card_track(evs), "log": card_log(evs),
        })
    cards.sort(key=lambda c: c["updated"], reverse=True)
    return cards


def runner_state(repo: Path) -> dict:
    lock = repo / "automation" / ".lock"
    return {"running": lock.is_file(), "pid": lock.read_text(encoding="utf-8").strip() if lock.is_file() else ""}


def sima_state(out_dir: Path, read_card=None, landed=None) -> list[dict]:
    """آخر إصدار لكل مشروع بخطواته. الخطوات من نموذج السجل نفسه (`timeline.progress`): كانت هنا تسع خطوات بلا الهوية وهناك
    اثنتا عشرة، فخالفت صفحة المشاريع السجل (م6 د). read_card: قارئ دفتر المشروع ليُعرف الدمج."""
    from .timeline import progress, reached  # السجل يستورد من هذا الملف: الاستيراد هنا يكسر الدورة

    runs = []
    if not out_dir.is_dir():
        return runs
    for project in sorted(p for p in out_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):  # _probe و_calibration مجلدات أدوات مؤقتة
        versions = sorted((p for p in project.iterdir() if p.is_dir() and p.name.startswith("v") and p.name[1:].isdigit()),
                          key=lambda p: int(p.name[1:]))
        if not versions:
            continue
        v = versions[-1]
        runs.append({"project": project.name, "version": v.name, "steps": progress(v, reached(v, read_card, landed))["steps"],
                     "audit": audit_state(v), **project_detail(v)})
    return runs


VERDICT_AR = {"approved": "اعتماد", "rejected": "رفض", "revise": "طلب تعديل", "switch_medium": "رسم جديد بوسيط"}
MEDIUM_AR_SHORT = {"abstract_mark": "علامة مجردة", "wordmark": "علامة كلامية", "emblem": "شارة", "pattern": "نمط"}
NAME_AR = {"clear": "متاح في المصادر المفحوصة", "conflict": "متعارض", "pending": "بانتظار التحقق"}


def _json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def cost_state(v: Path, ref: float | None = None) -> dict:
    """كلفة استدعاءات النموذج لإصدار: مجموع cost_usd في model_calls.jsonl مقابل مرجع التنبيه (ok < 70% ≤ warn < 100% ≤ over)."""
    ref = config.COST_REF_USD if ref is None else ref
    f = v / "model_calls.jsonl"
    rows = _read_jsonl(f) if f.is_file() else []
    usd = round(sum(float(r.get("cost_usd") or 0) for r in rows), 2)
    unknown = sum(1 for r in rows if r.get("cost_known") is False)  # استدعاء قُطع: كلفته محجوزه حدًّا أعلى لا ما صُرف
    level = "ok" if not ref or usd < ref * config.COST_WARN_RATIO else "warn" if usd < ref else "over"
    return {"usd": usd, "calls": len(rows), "ref": ref, "level": level, "unknown": unknown}


def audit_state(v: Path) -> dict:
    """ما اجتاز الفحص الحتمي وما ردّه في هذا الإصدار، من `work/audit.json`. الخطوات لا تحمل حالة «مردود»، فهذا ما تقوله
    اللقطة عن الفحص (م6 ط)."""
    rows = [r for r in _json(v / "work" / "audit.json").values() if isinstance(r, dict) and "passed" in r]
    return {"passed": sum(1 for r in rows if r["passed"]), "failed": sum(1 for r in rows if not r["passed"])}


def judge_state(v: Path, concept_id: str) -> dict:
    """درجة الحَكَم للمفهوم المعتمد من علامة القائمة المعروضة، مقابل العتبة. total=None إن لم تتوفر درجة."""
    total = (_json(v / "stages" / "shortlist.json").get("scores") or {}).get(concept_id) if concept_id else None
    return {"total": total, "bar": config.JUDGE_MIN_TOTAL, "below": total is not None and total < config.JUDGE_MIN_TOTAL}


def project_detail(v: Path) -> dict:
    """تفاصيل إصدار سِمة للمنصة: المفهوم المعتمد، القرارات، تحقق الاسم، الحزمة، التسليم. قراءة فقط."""
    rel = f"{v.parent.name}/{v.name}"
    run = _json(v / "run.json")
    brief = _json(v / "brief.json")
    concept = _json(v / "package" / "concept.json")
    decisions = []
    led = v / "decisions.jsonl"
    if led.is_file():
        for d in _read_jsonl(led):
            decisions.append({"at": d.get("at", ""), "verdict": d.get("verdict", ""),
                              "verdict_ar": VERDICT_AR.get(str(d.get("verdict")), str(d.get("verdict"))),
                              "concept": d.get("concept_id") or "", "medium_ar": MEDIUM_AR_SHORT.get(str(d.get("medium")), str(d.get("medium") or "")),
                              "reason": d.get("reason", "")})
    decisions.reverse()
    name = {}
    nc = v / "name_check.yaml"
    if nc.is_file():
        for line in nc.read_text(encoding="utf-8").splitlines():
            if ":" in line and not line.startswith((" ", "-")):
                k, _, val = line.partition(":")
                name[k.strip()] = val.strip().strip("'\"")
    pkg = v / "package"
    files = sorted(p.name for p in pkg.iterdir() if p.is_file()) if pkg.is_dir() else []
    mark = next((f for f in files if f.endswith("-lockup.svg")), None) or next((f for f in files if f.endswith("-mark.svg")), None)
    deliver = _json(v / "stages" / "deliver.json")
    return {
        "name_ar": brief.get("name_ar", v.parent.name), "short": brief.get("name_short", ""), "key": run.get("key", ""),
        "closed": bool(run.get("closed")), "base": rel,
        "preview": f"{rel}/preview.html" if (v / "preview.html").is_file() else "",
        "concept": {"id": concept.get("id", ""), "name": concept.get("name", ""), "sentence": concept.get("sentence", ""),
                    "medium_ar": MEDIUM_AR_SHORT.get(str(concept.get("medium")), "")} if concept else {},
        "mark": f"{rel}/package/{mark}" if mark else "",
        "files": [{"name": f, "href": f"{rel}/package/{f}"} for f in files],
        "decisions": decisions, "cost": cost_state(v), "judge": judge_state(v, concept.get("id", "")),
        "name_check": {"status": name.get("status", ""), "status_ar": NAME_AR.get(name.get("status", ""), "لم يُسجَّل"),
                       "at": name.get("checked_at", ""), "note": name.get("note", "")},
        "deliver": {"card": deliver.get("card_id", ""), "branch": deliver.get("branch", ""), "head": str(deliver.get("head", ""))[:8],
                    "in_place": str(deliver.get("commit", ""))[:8] if deliver.get("in_place") else "",
                    "manual": str(deliver.get("commit", ""))[:8] if deliver.get("manual") else "",
                    "repo": Path(str(deliver.get("repo", ""))).name if deliver.get("manual") else ""},
    }


def safe_out_path(out_dir: Path, rel: str) -> Path | None:
    """يحلّ مسارًا نسبيًا داخل out/ ويرفض الخروج منه. من work/ الداخلي لا يُخدم إلا ما يعرضه صندوق القرارات:
    <مشروع>/v<n>/work/concepts/<id>.svg ورسم عينات الطابع work/styles/<id>.svg ومصغّرات الورشة work/thumbs/<id>.svg ولوحات الاستكشاف work/explore/<id>.jpg، لا الطلبات
    ولا السجلات."""
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    if not parts or any(p in (".", "..") or p.startswith(".") for p in parts):
        return None
    low = [x.lower() for x in parts]  # NTFS لا يميّز حالة الأحرف: WORK هي work
    tail = low[2:] if low[0] == "_eval" else low  # تشغيلات تقييم الرسّام: _eval/<تشغيل>/<حالة>/v1/work/... بالقاعدة نفسها
    shown = len(tail) == 5 and tail[2] == "work" and (
        (tail[3] in ("concepts", "styles", "thumbs") and tail[4].endswith(".svg"))
        or (tail[3] == "explore" and tail[4].endswith((".jpg", ".png", ".webp"))))  # لوحات الاستكشاف النقطية: صور فقط، لا الموجز
    if "work" in low and not shown:
        return None
    root = out_dir.resolve()
    target = root.joinpath(*parts).resolve()
    if root not in target.parents or not target.is_file():
        return None
    return target


def without_hidden(state: dict, hidden: tuple[str, ...]) -> dict:
    """يُسقط مشاريع مخفية من حالة المنصة (السجلات والوارد والمهام). العرض فقط: لا يمسّ الملفات ولا الخط."""
    if not hidden:
        return state
    return {k: ([x for x in v if x.get("project") not in hidden] if k in ("sima", "inbox", "jobs", "workshop") else v) for k, v in state.items()}


def board_state(repo: Path | None, out_dir: Path, now: str, read_card=None, landed=None) -> dict:
    return {"now": now, "repo": str(repo) if repo else "", "sima": sima_state(out_dir, read_card, landed), "cards": ledger_state(repo) if repo else [],
            "runner": runner_state(repo) if repo else {"running": False, "pid": ""}}
