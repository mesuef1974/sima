"""ورشة الرسم (قرار المالك 2026-11-12): ما يُرسم الآن في آخر إصدار قبل أن يصل إلى قراره. عرض للقراءة فقط.

المالك كان لا يرى شيئًا حتى ينتهي الحَكَم (أفضل ثلاثة)، والدورة تستغرق ساعة فأكثر. الورشة تعرض مصغّرات الأفكار بما قرأه القارئ
الأعمى ثم المفاهيم الخمسة وهي تُنقد وتُصقل. لا قرار عليها ولا رمز: القرار يبقى على بطاقة المفاهيم بعد الحَكَم، وحين تظهر تلك
البطاقة تختفي الورشة. ملف يكتبه النموذج في أثناء القراءة (YAML ناقص) لا يُسقط الصفحة: يُتجاوز حتى يكتمل.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import yaml

from . import blind, designer, drawer_eval, thumbs
from .ledger import Ledger
from .protocol import merged_digest, read_concept_svgs, read_concepts, read_ideas, read_small_svgs
from .timeline import _request_label
from .workspace import Workspace, _versions, workspace_of

READ_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError)  # ملف في منتصف كتابته: عرض فقط
EXPLORE_IMG = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}\.(jpg|png|webp)")
THUMB_STATE_AR = {"allowed": "مجتازة", "blocked": "مردودة", "weak": "ضعيفة", "": "لم تُقرأ بعد"}
EVAL_DIR = "_eval"
EVAL_SHOWN_S = 24 * 3600  # آخر تشغيل تقييم يبقى معروضًا يومًا بعد آخر رسم فيه، ثم تخلو له صفحة «اليوم»
EVAL_JUDGED = "حكم الحَكَم الأول"
EVAL_HIDDEN = ".hidden"  # علامة في مجلد التشغيل: أخفاه المالك من الورشة قبل انقضاء يومه (`sima eval hide`)


def _safe(fn, default):
    try:
        return fn()
    except READ_ERRORS:
        return default


def _img(ws: Workspace, rel: str, folder: str, name: str) -> tuple[str, int]:
    f = ws.work / folder / name
    return (f"{rel}/work/{folder}/{name}", f.stat().st_mtime_ns // 1_000_000) if f.is_file() else ("", 0)


def _thumbs(ws: Workspace, rel: str) -> list[dict]:
    m = ws.read_marker(thumbs.KIND)
    allowed, blocked, weak, seen = m.get("allowed") or [], m.get("blocked") or {}, m.get("weak") or {}, m.get("seen") or {}
    out = []
    for i in _safe(lambda: read_ideas(ws), []):
        img, stamp = _img(ws, rel, "thumbs", f"{i.id}.svg")
        if not img:
            continue
        state = "blocked" if i.id in blocked else "weak" if i.id in weak else "allowed" if i.id in allowed else ""
        out.append({"id": i.id, "sentence": i.sentence, "img": img, "stamp": stamp, "state": state, "state_ar": THUMB_STATE_AR[state],
                    "seen": str(seen.get(i.id, ""))})
    order = {"allowed": 0, "": 1, "weak": 2, "blocked": 3}
    return sorted(out, key=lambda t: (order[t["state"]], allowed.index(t["id"]) if t["id"] in allowed else 0))


def _concepts(ws: Workspace, rel: str) -> list[dict]:
    concepts = _safe(lambda: read_concepts(ws), [])
    if not concepts:
        return []
    ids = [c.id for c in concepts]
    dg = _safe(lambda: merged_digest(read_concept_svgs(ws, concepts), read_small_svgs(ws, concepts)), "")
    r = _safe(lambda: blind.read(ws, dg, ids), None) if dg else None  # قراءة المحتوى المعروض نفسه لا قراءة رسم سابق
    out = []
    for c in concepts:
        img, stamp = _img(ws, rel, "concepts", f"{c.id}.svg")
        reading = r.readings.get(c.id) if r else None
        out.append({"id": c.id, "name": c.name, "sentence": c.sentence, "idea": c.idea_id or "", "img": img, "stamp": stamp,
                    "seen": reading.line() if reading else "", "misread": bool(reading and reading.blocked)})
    return out


def _explore(ws: Workspace, rel: str) -> list[dict]:
    """لوحات استكشاف الاتجاهات (تجربة بقرار المالك 2026-11-12): صور نقطية يصفها `work/explore/boards.yaml`. عرض فقط."""
    data = _safe(lambda: yaml.safe_load((ws.work / "explore" / "boards.yaml").read_text(encoding="utf-8")), None)
    boards = data.get("boards") if isinstance(data, dict) else None
    out = []
    for b in boards if isinstance(boards, list) else []:
        name = str(b.get("img", "")) if isinstance(b, dict) else ""
        if not EXPLORE_IMG.fullmatch(name):
            continue
        img, stamp = _img(ws, rel, "explore", name)
        if img:
            out.append({"id": str(b.get("id", "")), "name": str(b.get("name", "")), "detail": str(b.get("detail", "")),
                        "misread": str(b.get("misread", "")), "img": img, "stamp": stamp, "source": str(data.get("source", ""))})
    return out


def _stage(ws: Workspace) -> str:
    reqs = sorted(ws.work.glob("REQUEST-*.md"), key=lambda p: p.stat().st_mtime) if ws.work.is_dir() else []
    return _request_label(reqs[-1].stem) if reqs else ""


def _eval_runs(out_dir: Path) -> list[Path]:
    root = out_dir / EVAL_DIR
    return sorted(d for d in root.iterdir() if d.is_dir()) if root.is_dir() else []


def hide_eval(out_dir: Path) -> str | None:
    """يُخفي آخر تشغيل تقييم من الورشة قبل انقضاء يومه (قرار المالك 2026-11-13): علامة في مجلده، فالإخفاء لذلك التشغيل
    وحده ولا يُمسّ من أعماله شيء؛ والتشغيل التالي يُعرض كعادته. يعيد معرّف التشغيل، أو None إن لم يوجد تشغيل."""
    runs = _eval_runs(out_dir)
    if not runs:
        return None
    (runs[-1] / EVAL_HIDDEN).write_text("", encoding="utf-8")
    return runs[-1].name


def _eval(out_dir: Path, now: float) -> list[dict]:
    """آخر تشغيل لمجموعة تقييم الرسّام (قرار المالك 2026-11-13): حالاته الخيالية بمصغّراتها ومفاهيمها ودرجة الحَكَم الأولى.
    عرض فقط كبقية الورشة؛ ليست مشاريع ولا قرار عليها، ولذلك تحمل مفتاح `eval` وتُعنون بغير عنوان المشاريع."""
    runs = _eval_runs(out_dir)
    if runs and (runs[-1] / EVAL_HIDDEN).is_file():
        return []
    out = []
    for d in sorted(runs[-1].iterdir()) if runs else []:
        v = d / "v1"
        ws = _safe(lambda v=v: workspace_of(v), None) if (v / "run.json").is_file() else None
        if ws is None:
            continue
        rel = f"{EVAL_DIR}/{runs[-1].name}/{d.name}/v1"
        ts, cs = _thumbs(ws, rel), _concepts(ws, rel)
        if not (ts or cs):
            continue
        j = _safe(lambda ws=ws: drawer_eval.first_judgement(ws), None)
        scores = {cid: {"score": s.total, "passed": s.passed} for cid, s in j.scores.items()} if j else {}
        name = _safe(lambda v=v: str(json.loads((v / "brief.json").read_text(encoding="utf-8"))["name_ar"]), d.name)
        out.append({"project": d.name, "version": 1, "stage": EVAL_JUDGED if scores else _stage(ws), "thumbs": ts,
                    "concepts": [c | scores.get(c["id"], {}) for c in cs], "explore": [], "eval": {"run": runs[-1].name, "name": name}})
    newest = max((x["stamp"] for w in out for x in (*w["thumbs"], *w["concepts"])), default=0) / 1000
    return out if now - newest <= EVAL_SHOWN_S else []


def workshop(out_dir: Path, inbox: list[dict], now: float | None = None) -> list[dict]:
    """لكل مشروع مفتوح بلا مفهوم معتمد ولا بطاقة مفاهيم معروضة: ما في ورشته الآن. الفارغ لا يُعاد. وبعدها آخر تشغيل تقييم."""
    shown = {i["project"] for i in inbox if i.get("kind") == "concepts"}
    out = []
    for d in sorted(out_dir.iterdir()) if out_dir.is_dir() else []:
        versions = _versions(d) if d.is_dir() and not d.name.startswith(("_", ".")) else []
        if not versions or d.name in shown or not (versions[-1][1] / "run.json").is_file():
            continue
        n, v = versions[-1]
        ws = _safe(lambda v=v: workspace_of(v), None)
        if ws is None:
            continue
        approved = _safe(lambda ws=ws: Ledger(ws.ledger_path).approved(), None) is not None
        # المسار الخارجي يعتمد المفهوم باختيار السكتش، فلا يرى المالك المتجه المستلم قبل الدليل: يُعرض هنا حتى تُبنى الهوية
        external = approved and designer.frozen_enabled(v) and not ws.done("identity_build")
        if approved and not external:
            continue
        rel = f"{d.name}/v{n}"
        ts, cs, ex = _thumbs(ws, rel), _concepts(ws, rel), _explore(ws, rel)
        if ts or cs or ex:
            out.append({"project": d.name, "version": n, "stage": _stage(ws), "thumbs": ts, "concepts": cs, "explore": ex}
                       | ({"designer": True} if external else {}))
    return out + _safe(lambda: _eval(out_dir, time.time() if now is None else now), [])
