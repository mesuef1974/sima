"""بوابة الطابع البصري: عينات اسم العلامة بستة أساليب ثابتة، واختيار المالك منها قيدًا على الرسّام والحَكَم.

العينات يرسمها النموذج (REQUEST-style.md) في work/styles/<id>.mark.yaml والأداة تبنيها؛ الكتالوج نفسه ثابت في config
فلا يخترع النموذج أساليب. الاختيار مربوط ببصمة العينات المعروضة في style_decisions.jsonl، وآخر سطر هو النافذ.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from .. import config
from ..domain import Brief
from . import live_preview
from .protocol import compile_dir, svgs_digest
from .workspace import Workspace

SHAPE = re.compile(r"<(path|rect|circle|ellipse|polygon)\b", re.IGNORECASE)
FORBIDDEN = re.compile(r"<(text|linearGradient|radialGradient|filter|image|script)\b", re.IGNORECASE)


def styles_dir(ws: Workspace) -> Path:
    return ws.work / "styles"


def decisions_path(ws: Workspace) -> Path:
    return ws.root / "style_decisions.jsonl"


def catalog() -> dict[str, tuple[str, str]]:
    return {sid: (name, principle) for sid, name, principle in config.STYLES}


def choices(ws: Workspace) -> list[dict]:
    p = decisions_path(ws)
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def current(ws: Workspace) -> dict | None:
    c = choices(ws)
    return c[-1] if c else None


def samples(ws: Workspace) -> dict[str, str]:
    d = styles_dir(ws)
    return {sid: (d / f"{sid}.svg").read_text(encoding="utf-8") for sid in catalog() if (d / f"{sid}.svg").is_file()}


def digest(ws: Workspace) -> str:
    return svgs_digest(samples(ws))


def compile_samples(ws: Workspace, build) -> dict[str, str]:
    d = styles_dir(ws)
    if build is None or not d.is_dir():
        return {}
    return compile_dir(d, build, {sid: name for sid, (name, _) in catalog().items()})


def validate(ws: Workspace, build_errors: dict[str, str]) -> list[str]:
    """ما ينقص كي تُعرض العينات: عينة لكل أسلوب، صالحة، بلا نص حي ولا تدرجات ولا فلاتر، ومختلفة عن غيرها."""
    problems: list[str] = []
    got = samples(ws)
    for sid, (name, _) in catalog().items():
        if sid in build_errors:
            problems.append(f"{sid} «{name}»: خطأ بناء: {build_errors[sid]}")
        elif sid not in got:
            problems.append(f"{sid} «{name}»: لا عينة (work/styles/{sid}.mark.yaml)")
        elif "viewBox" not in got[sid] or not SHAPE.search(got[sid]):
            problems.append(f"{sid} «{name}»: SVG بلا viewBox أو بلا شكل")
        elif FORBIDDEN.search(got[sid]):
            problems.append(f"{sid} «{name}»: نص حي أو تدرج أو فلتر أو صورة")
    seen: dict[str, str] = {}
    for sid, svg in got.items():
        if svg in seen:
            problems.append(f"{sid} تطابق {seen[svg]} حرفيًا: لكل أسلوب رسم مستقل")
        seen.setdefault(svg, sid)
    return problems


def record(ws: Workspace, picked: list[str], note: str, shown_digest: str) -> dict:
    cat = catalog()
    if not 1 <= len(picked) <= config.STYLE_PICK_MAX or len(set(picked)) != len(picked) or any(p not in cat for p in picked):
        raise ValueError(f"اختر من 1 إلى {config.STYLE_PICK_MAX} من الأساليب المعروضة.")
    row = {"styles": picked, "note": note.strip(), "digest": shown_digest, "at": datetime.now(UTC).isoformat(timespec="seconds")}
    with decisions_path(ws).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def lines(ws: Workspace) -> list[str]:
    """قيد الطابع في كل طلب رسم وتحكيم: ما اختاره المالك بنصه، وعيّناته مرجعًا للروح لا للنسخ."""
    c = current(ws)
    if c is None:
        return []
    cat = catalog()
    out = ["## الطابع الذي اختاره المالك (قيد ملزم)",
           *[f"- «{cat[s][0]}»: {cat[s][1]}. العينة: work/styles/{s}.svg" for s in c["styles"] if s in cat]]
    if c.get("note"):
        out.append(f"- ملاحظة المالك: {c['note']}")
    out += ["كل مفهوم ينتمي بوضوح إلى هذا الطابع (أو يجمع الاثنين إن اختار اثنين)، بفكرة وحيلة خاصة به لا بتكرار العينة.",
            "والحَكَم يخفض «modern» و«meaning» لكل مفهوم خارج الطابع المختار.", ""]
    return out


def write_request(ws: Workspace, brief: Brief, problems: list[str], history: list[str]) -> Path:
    name = brief.name_short or brief.name_ar
    rows = [f"- `{sid}` «{n}»: {p}" for sid, (n, p) in catalog().items()]
    text = "\n".join([
        f"# طلب عينات الطابع البصري: {brief.name_ar}", "",
        f"المالك سيختار من هذه العينات ما يعنيه «الحديث والمبتكر» عنده قبل رسم المفاهيم. ارسم الاسم «{name}» كاملًا مقروءًا",
        "بكل أسلوب من الستة أدناه، بأعلى مستوى احترافي تستطيعه في ذلك الأسلوب: عينة تبيع الأسلوب لا مسودة.",
        "اقرأ `.claude/skills/sima-design/references/40-professional-bar.md` و`41-construction.md` أولًا،"
        " ثم `45-drawer-profile.md` (دورك) و`42-arabic-lettering.md` (الحرف المخصّص).", "",
        "## المطلوب",
        "لكل أسلوب `work/styles/<id>.mark.yaml` بصيغة أداة البناء (`width` و`height` عريضتان مع `fit`)، والأداة تولّد `<id>.svg`.",
        "الكلمة تُشكَّل حروفًا حقيقية بشكل `text` في أداة البناء (خط من fonts/) ثم تُعدَّل هندسيًا، أو تُبنى",
        "من الصفر على شبكة. أسود فقط، بلا نص حي ولا تدرجات ولا فلاتر. لا تكتب شيئًا خارج work/styles/.", "",
        *live_preview.lines("styles"),
        "## الأساليب (ثابتة، لا تضف ولا تحذف)", *rows, "",
        "## الموجز",
        f"- الغرض: {brief.purpose}", f"- الكلمات الثلاث: {'، '.join(brief.three_words)}", f"- الإحساس: {brief.taste.feeling}",
        "- ممنوع: " + "؛ ".join(list(brief.taste.avoid) + list(brief.taste.dislikes)), "",
        *history,
        "## ما ينقص الآن", *[f"- {p}" for p in problems], "",
        "ثم أعد تشغيل: `uv run sima run <brief>`",
    ])
    return ws.write_request("REQUEST-style.md", text)
