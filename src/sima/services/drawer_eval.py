"""مجموعة تقييم الرسّام: حالات ثابتة يُشغَّل عليها خط الرسم نفسه، وتُجمع منها أرقام تُقارَن بين تشغيلين.

الغرض أن يُحكم على تغيير في الرسّام (نموذجه أو جهده أو مراجعه أو صياغة طلبه) بأرقام من الخط لا بانطباع عن مشروع واحد.
الحالة موجز خيالي في `evals/drawer/cases/` معه طابع ثابت (`eval.styles`)، فلا عينات تُرسم ولا مالك يُنتظر. والتشغيل يقف عند
أول حكم مستقل (`judge`) أو عند اختيار المصغّرات (`thumbs`، أرخص)، فلا صقل آلي ولا معاينة.

لا شيء هنا يحكم على الجودة بنفسه: الأرقام مما كتبه الخط (فحوص الأداة، والقارئ الأعمى، والحَكَم المستقل، وسجل الاستدعاءات).
درجات الحَكَم متذبذبة بطبعها؛ فرق صغير بين تشغيلين لا يُقرأ حُكمًا.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

import yaml

from .. import config
from ..domain import Brief, brief_from_dict
from . import blind, protocol, style, thumbs
from . import judge as judging
from .pipeline import AWAIT_MODEL, AWAIT_OWNER, Outcome
from .workspace import Workspace

UNTIL = ("judge", "thumbs")
STOP = "بلغ التشغيل نقطة التقييم"
STYLE_DIGEST = "eval"  # قرار الطابع من الحالة لا من عينات معروضة


class EvalError(ValueError):
    """حالة تقييم ناقصة أو معرّف مجهول؛ برسالة عربية."""


@dataclass(frozen=True)
class Case:
    id: str
    brief: Brief
    styles: tuple[str, ...]


def load_cases(cases_dir: Path, only: Iterable[str] = ()) -> list[Case]:
    cases = []
    for p in sorted(cases_dir.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        brief = brief_from_dict(data, source=str(p))
        styles = tuple(str(s) for s in ((data.get("eval") or {}).get("styles") or ()))
        known = style.catalog()
        if brief.project != p.stem:
            raise EvalError(f"{p.name}: project يجب أن يطابق اسم الملف ({p.stem})")
        if not 1 <= len(styles) <= config.STYLE_PICK_MAX or any(s not in known for s in styles):
            raise EvalError(f"{p.name}: eval.styles يلزمه أسلوب أو اثنان من {', '.join(known)}")
        if brief.identity.enabled:
            raise EvalError(f"{p.name}: حالات التقييم للعلامة وحدها (بلا identity)")
        cases.append(Case(p.stem, brief, styles))
    wanted = list(only)
    unknown = [w for w in wanted if w not in {c.id for c in cases}]
    if unknown:
        raise EvalError(f"حالة مجهولة: {', '.join(unknown)}. المتاح: {', '.join(c.id for c in cases)}")
    return [c for c in cases if not wanted or c.id in wanted]


def prepare(ws: Workspace, case: Case) -> None:
    """قرار الطابع ثابت في الحالة: يُسجَّل قبل أول تشغيل، فلا تُرسم العينات ولا ينتظر الخط مالكًا."""
    if not style.choices(ws):
        style.record(ws, list(case.styles), "حالة تقييم: طابع ثابت", STYLE_DIGEST)


def _concept_ids(ws: Workspace) -> list[str]:
    if not (ws.work / "concepts.yaml").is_file():
        return []
    try:
        return [c.id for c in protocol.read_concepts(ws)]
    except Exception:  # noqa: BLE001 — ملف مفاهيم ناقص في منتصف التشغيل: لا مفاهيم تُقاس بعد
        return []


def first_judgement(ws: Workspace) -> judging.Judgement | None:
    """أول حكم مكتمل في الدورة: درجات لكل المفاهيم بلا نواقص."""
    ids = _concept_ids(ws)
    d = judging.judge_dir(ws)
    for p in sorted(d.glob("*.yaml"), key=lambda x: x.stat().st_mtime) if ids and d.is_dir() else []:
        j = judging.read(ws, p.stem, ids)
        if j is not None and not j.problems:
            return j
    return None


def reached(ws: Workspace, until: str) -> bool:
    if until == "thumbs":
        return ws.done(thumbs.KIND)
    return first_judgement(ws) is not None


def stepper(run: Callable[[], Outcome], until: str) -> Callable[[], Outcome]:
    """خطوة الخط كما هي، وتقف عند نقطة التقييم بدل أن تطلب من النموذج ما بعدها (رسمًا بعد المصغّرات أو صقلًا بعد الحكم)."""
    def step() -> Outcome:
        out = run()
        if out.code == AWAIT_MODEL and reached(out.workspace, until):
            return Outcome(AWAIT_OWNER, STOP, out.workspace)
        return out
    return step


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()] if p.is_file() else []


def _mean(xs: Iterable[float]) -> float | None:
    xs = list(xs)
    return round(fmean(xs), 2) if xs else None


def _kind(request: str) -> str:
    """نوع الطلب بلا رقم الجولة: REQUEST-critique-r2.md ← critique."""
    return re.sub(r"-r\d+$", "", request.removeprefix("REQUEST-").removesuffix(".md"))


def stop_reason(message: str) -> str:
    """سبب التوقف: آخر سطر في الرسالة. التشغيل الآلي يضيف سببه (سقف الإنفاق أو الاستدعاءات) بعد ما كان الخط ينتظره، فالسطر الأول وحده
    كان يُسقط السبب ويُظهر حالة لم تبلغ بلا علّة."""
    lines = [ln for ln in message.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def cap_warning(results: Iterable[dict], until: str, case_usd: float) -> str | None:
    """سقف الحالة مقيسًا بما أنفقته تشغيلات سابقة حتى نقطة التوقف نفسها: حالة بلغتها بكلفة تفوق السقف، أو حالة وقفت دونها بعد إنفاق
    يبلغه. بلا قياس سابق لا تحذير: لا يُخمَّن."""
    reached, short = [], []
    for run in results:
        if run.get("until") != until:
            continue
        for c in run.get("cases", []):
            (reached if c.get("reached") else short).append(float(c.get("cost_usd") or 0))
    need = max(reached, default=0.0)
    floor = max(short, default=0.0)
    if need > case_usd:
        return (f"تحذير: سقف الحالة {case_usd:g}$ دون ما أنفقته حالة بلغت نقطة «{until}» في تشغيل سابق ({need:g}$)؛ "
                "قد تقف الحالات دونها. ارفعه بـ --case-usd إن أردت بلوغها.")
    if floor >= case_usd * 0.9:
        return (f"تحذير: حالة في تشغيل سابق أنفقت {floor:g}$ ولم تبلغ نقطة «{until}»، وسقف الحالة {case_usd:g}$ لا يزيد عليها؛ "
                "المرجّح أن تقف دونها ثانية. ارفعه بـ --case-usd إن أردت بلوغها.")
    return None


def collect(ws: Workspace, case_id: str, until: str, message: str, cap_usd: float | None = None) -> dict:
    """أرقام حالة واحدة مما كتبه الخط في إصدارها. `stopped` الرسالة كاملة بسببها، و`cap_usd` سقف إنفاق هذه الحالة كما طُبّق."""
    calls = _jsonl(ws.root / "model_calls.jsonl")
    by_kind: dict[str, dict] = {}
    for c in calls:
        k = by_kind.setdefault(_kind(str(c.get("request", ""))), {"calls": 0, "cost_usd": 0.0})
        k["calls"] += 1
        k["cost_usd"] = round(k["cost_usd"] + float(c.get("cost_usd") or 0), 4)
    models = sorted({m for c in calls for m in (c.get("models_used") or [c.get("model") or ""]) if m})
    ids = _concept_ids(ws)
    out: dict = {
        "case": case_id, "reached": reached(ws, until), "stopped": message, "cap_usd": cap_usd,
        "calls": len(calls), "cost_usd": round(sum(float(c.get("cost_usd") or 0) for c in calls), 2),
        "seconds": round(sum(float(c.get("seconds") or 0) for c in calls)), "requests": by_kind, "models": models,
        "thumbs": None, "concepts": len(ids), "audit_passed": None, "critique_rounds": protocol.critique_rounds_done(ws),
        "blind": None, "judge": None,
    }
    th = ws.read_marker(thumbs.KIND)
    if th:
        blocked = {**(th.get("blocked") or {}), **(th.get("weak") or {})}
        reach = list((th.get("reach") or {}).values())
        out["thumbs"] = {"ideas": len(th.get("allowed") or []) + len(blocked), "blocked": len(blocked),
                         "exhausted": bool(th.get("exhausted")), "reach_mean": _mean(reach)}
    audit = ws.work / "audit.json"
    if ids and audit.is_file():
        rows = json.loads(audit.read_text(encoding="utf-8"))
        out["audit_passed"] = sum(1 for i in ids if (rows.get(i) or {}).get("passed"))
    d = blind.blind_dir(ws)
    for p in sorted(d.glob("*.yaml"), key=lambda x: x.stat().st_mtime) if ids and d.is_dir() else []:
        r = blind.read(ws, p.stem, ids)
        if r is not None and not r.problems:  # القراءة الأولى: ما رآه القارئ قبل أي تصحيح
            out["blind"] = {"read": len(r.readings), "blocked": len(r.blocked())}
            break
    j = first_judgement(ws)
    if j is not None:
        scores = list(j.scores.values())
        out["judge"] = {
            "concepts": {s.concept_id: {"total": s.total, "passed": s.passed, "scores": s.scores} for s in scores},
            "mean_total": _mean(s.total for s in scores), "best_total": max(s.total for s in scores),
            "passed": sum(1 for s in scores if s.passed),
            "criteria": {k: _mean(s.scores[k] for s in scores) for k in config.JUDGE_CRITERIA},
        }
    return out


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def summarize(run_id: str, at: str, label: str, until: str, meta: dict, cases: list[dict]) -> dict:
    judged = [c["judge"] for c in cases if c["judge"]]
    th = [c["thumbs"] for c in cases if c["thumbs"]]
    bl = [c["blind"] for c in cases if c["blind"]]
    drawn = [c for c in cases if c["audit_passed"] is not None]
    totals = {
        "cases": len(cases), "reached": sum(1 for c in cases if c["reached"]),
        "calls": sum(c["calls"] for c in cases), "cost_usd": round(sum(c["cost_usd"] for c in cases), 2),
        "judge_mean": _mean(j["mean_total"] for j in judged), "judge_best_mean": _mean(j["best_total"] for j in judged),
        "pass_rate": _rate(sum(j["passed"] for j in judged), sum(len(j["concepts"]) for j in judged)),
        "criteria": {k: _mean(j["criteria"][k] for j in judged) for k in config.JUDGE_CRITERIA} if judged else {},
        "thumb_block_rate": _rate(sum(t["blocked"] for t in th), sum(t["ideas"] for t in th)),
        "blind_block_rate": _rate(sum(b["blocked"] for b in bl), sum(b["read"] for b in bl)),
        "audit_pass_rate": _rate(sum(c["audit_passed"] for c in drawn), sum(c["concepts"] for c in drawn)),
    }
    return {"run": run_id, "at": at, "label": label, "until": until, "config": meta, "cases": cases, "totals": totals}


ROWS = (
    ("judge_mean", "متوسط مجموع الحَكَم (من 40)", True), ("judge_best_mean", "متوسط أفضل مفهوم في الحالة", True),
    ("pass_rate", "نسبة المفاهيم المجتازة للعتبة", True), ("thumb_block_rate", "نسبة المصغّرات المردودة عند القارئ", False),
    ("blind_block_rate", "نسبة المفاهيم المردودة عند القارئ", False), ("audit_pass_rate", "نسبة المفاهيم المجتازة للفحوص", True),
    ("cost_usd", "الكلفة بالدولار", False), ("calls", "عدد الاستدعاءات", False),
)


def _fmt(v: object) -> str:
    return "—" if v is None else f"{v:g}" if isinstance(v, (int, float)) else str(v)


def report(s: dict) -> list[str]:
    """ملخص تشغيل واحد بسطور عربية."""
    t = s["totals"]
    lines = [f"تشغيل {s['run']} · حتى {s['until']} · {t['reached']} من {t['cases']} بلغت نقطة التقييم" + (f" · {s['label']}" if s["label"] else "")]
    lines += [f"  {title}: {_fmt(t[key])}" for key, title, _ in ROWS]
    if t["criteria"]:
        lines.append("  المعايير: " + "، ".join(f"{k} {_fmt(v)}" for k, v in t["criteria"].items()))
    for c in s["cases"]:
        j = c["judge"]
        judge = f"الحَكَم متوسط {_fmt(j['mean_total'])} وأفضل {j['best_total']} ومجتاز {j['passed']}" if j else "بلا حكم"
        lines.append(f"  - {c['case']}: {judge} · {c['calls']} استدعاء · {c['cost_usd']:g}$" + ("" if c["reached"] else f" · لم تبلغ: {stop_reason(c['stopped'])}"))
    return lines


def compare(a: dict, b: dict) -> list[str]:
    """فرق تشغيلين (ب ناقص أ) على المقاييس المشتركة، مع ما يمنع قراءة الفرق حُكمًا."""
    lines = [f"المقارنة: {a['run']} ← {b['run']}"]
    ids_a, ids_b = [c["case"] for c in a["cases"]], [c["case"] for c in b["cases"]]
    if a["until"] != b["until"]:
        lines.append(f"تنبيه: نقطة التوقف مختلفة ({a['until']} و{b['until']})؛ الأرقام لا تتقابل.")
    if ids_a != ids_b:
        lines.append("تنبيه: الحالات مختلفة بين التشغيلين؛ قارن الحالات المشتركة سطرًا بسطر.")
    if (a["config"].get("judge_model"), a["config"].get("bar")) != (b["config"].get("judge_model"), b["config"].get("bar")):
        lines.append("تنبيه: الحَكَم أو العتبة تغيّرا بين التشغيلين؛ فرق الدرجات قد يكون من الحَكَم لا من الرسّام.")
    for key, title, higher_better in ROWS:
        x, y = a["totals"].get(key), b["totals"].get(key)
        if x is None or y is None:
            lines.append(f"  {title}: {_fmt(x)} ← {_fmt(y)}")
            continue
        d = round(y - x, 3)
        mark = "" if not d else " (أفضل)" if (d > 0) == higher_better else " (أسوأ)"
        lines.append(f"  {title}: {_fmt(x)} ← {_fmt(y)} · الفرق {d:+g}{mark}")
    by_b = {c["case"]: c for c in b["cases"]}
    for c in a["cases"]:
        o = by_b.get(c["case"])
        if o and c["judge"] and o["judge"]:
            lines.append(f"  - {c['case']}: متوسط الحَكَم {_fmt(c['judge']['mean_total'])} ← {_fmt(o['judge']['mean_total'])}، "
                         f"الأفضل {c['judge']['best_total']} ← {o['judge']['best_total']}")
    lines.append("درجات الحَكَم متذبذبة ولم يُقَس تذبذبها هنا: شغّل الإعداد نفسه مرتين لتعرف الفرق الذي يُعتدّ به قبل أن تحكم بهذا الفرق.")
    return lines
