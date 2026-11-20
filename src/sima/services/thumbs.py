"""مصغّرات الأفكار: الأفكار تُختار بما يُرى منها لا بما كُتب عنها.

قبل رسم المفاهيم الخمسة يرسم الرسّام لكل فكرة في ideas.yaml مصغّرة سريعة (`work/thumbs/<idea_id>.mark.yaml`)، ويقرؤها القارئ
الأعمى (services/blind.py، نوع thumbs) بلا اسم ولا فكرة. الفكرة التي تُقرأ حرفًا أجنبيًا أو رمزًا شائعًا أو أيقونة واجهة تُردّ
قبل أن يُنفق عليها رسم كامل وجولات تحكيم، والباقية تُرتَّب بقرب ما رآه القارئ مما قصده الرسّام (نموذج التضمين المحلي إن وُجد)،
ومنها وحدها تُرسم المفاهيم. سبب وجودها: في سِمة v2 اختيرت خمس أفكار من ثماني عشرة جملة، ورُسمت الخمس وحدها، فنالت الفكرة
2–3 من 5 عند الحَكَم ونالت علامات مرجعية 4؛ المحترف يختار من مصغّرات مرسومة.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .. import config
from ..domain import Idea
from . import blind, live_preview, novelty
from .ports import Embedder, Renderer
from .protocol import compile_dir, ideas_problems, read_concepts, svgs_digest
from .workspace import Workspace

KIND = "thumbs"
REQUEST = "REQUEST-thumbs.md"
BLIND_REQUEST = "REQUEST-blind-thumbs.md"


@dataclass
class Selection:
    allowed: list[str] = field(default_factory=list)  # مرتّبة: الأقرب إلى قصد الرسّام أولًا إن قيس، وإلا بترتيب ideas.yaml
    blocked: dict[str, str] = field(default_factory=dict)  # المعرّف ← ما رآه القارئ
    seen: dict[str, str] = field(default_factory=dict)
    reach: dict[str, float] = field(default_factory=dict)  # تشابه ما رُئي مع جملة الفكرة (0–1)؛ فارغ بلا نموذج تضمين


def thumbs_dir(ws: Workspace) -> Path:
    return ws.work / KIND


def images(ws: Workspace, idea_id: str) -> list[Path]:
    d = ws.render_dir / KIND / idea_id
    return [d / f"{n}.png" for n in config.THUMB_SIZES]


def compile_specs(ws: Workspace, build) -> dict[str, str]:
    d = thumbs_dir(ws)
    return compile_dir(d, build, {}) if d.is_dir() else {}


def validate(ws: Workspace, errors: dict[str, str]) -> tuple[list[Idea], list[str]]:
    """ما ينقص كي تُقرأ المصغّرات: ملف أفكار صالح بعدده وحِيَله، ومصغّرة مبنية بلا خطأ لكل فكرة."""
    ideas, problems = ideas_problems(ws)
    d = thumbs_dir(ws)
    for i in ideas:
        if i.id in errors:
            problems.append(f"خطأ في بناء work/thumbs/{i.id}.mark.yaml: {errors[i.id]}")
        elif not (d / f"{i.id}.svg").is_file():
            problems.append(f"لا مصغّرة للفكرة {i.id} (work/thumbs/{i.id}.mark.yaml)")
    return ideas, problems


def svgs(ws: Workspace, ideas: list[Idea]) -> dict[str, str]:
    d = thumbs_dir(ws)
    return {i.id: (d / f"{i.id}.svg").read_text(encoding="utf-8") for i in ideas if (d / f"{i.id}.svg").is_file()}


def digest(built: dict[str, str]) -> str:
    return svgs_digest(built)


def render(ws: Workspace, renderer: Renderer, built: dict[str, str]) -> None:
    """صور المصغّرات في work/render/thumbs/<id>/ (ما يقرؤه القارئ الأعمى وحده)؛ يُعاد بناء المجلد كاملًا لكل محتوى جديد."""
    root = ws.render_dir / KIND
    shutil.rmtree(root, ignore_errors=True)
    for iid, svg in built.items():
        out = root / iid
        out.mkdir(parents=True, exist_ok=True)
        for size in config.THUMB_SIZES:
            (out / f"{size}.png").write_bytes(renderer.render_png(svg, size, "#FFFFFF"))


def select(readings: blind.Readings, ideas: list[Idea], embedder: Embedder | None = None) -> Selection:
    """الردّ حتمي من تصنيف القارئ. الترتيب بقرب ما رُئي من جملة الفكرة وحيلتها إن توفّر نموذج التضمين (إرشاد للرسّام لا بوابة)."""
    sel = Selection()
    for i in ideas:
        r = readings.readings.get(i.id)
        if r is None:
            continue
        sel.seen[i.id] = r.line()
        if r.blocked:
            sel.blocked[i.id] = r.line()
        else:
            sel.allowed.append(i.id)
    kept = [i for i in ideas if i.id in sel.allowed]
    vecs = embedder.embed([f"{i.sentence} {i.twist}" for i in kept] + [readings.readings[i.id].seen for i in kept]) if embedder and kept else None
    if vecs is not None and len(vecs) == 2 * len(kept):
        sel.reach = {i.id: round(novelty.cosine(vecs[n], vecs[n + len(kept)]), 3) for n, i in enumerate(kept)}
        sel.allowed.sort(key=lambda iid: -sel.reach[iid])
    return sel


def marker(sel: Selection, built_digest: str, exhausted: bool) -> dict:
    """علامة المرحلة. عند استنفاد الجولات دون خمس مجتازة لا تُفرض قائمة الردّ (وإلا تعذّر رسم خمسة) ويُنبَّه الرسّام."""
    return {"digest": built_digest, "allowed": sel.allowed, "blocked": {} if exhausted else sel.blocked,
            "weak": sel.blocked if exhausted else {}, "seen": sel.seen, "reach": sel.reach, "exhausted": exhausted}


def lines(ws: Workspace) -> list[str]:
    """قسم طلبات الرسم والصقل: ما اجتاز القراءة العمياء وما رُدّ، بنص ما رآه القارئ."""
    m = ws.read_marker(KIND)
    if not m:
        return []
    seen, reach = m.get("seen") or {}, m.get("reach") or {}
    out = ["## الأفكار بعد القراءة العمياء للمصغّرات",
           "قارئ مستقل لم يُعطَ الاسم ولا الفكرة قرأ مصغّرة كل فكرة. ارسم المفاهيم من المجتازة وحدها، وقدّم منها ما رأى القارئ فيه",
           "ما قصدتَه؛ ومصغّرة الفكرة في `work/thumbs/<id>.mark.yaml` نقطة بدء لبنائها لا بناء نهائي.",
           "المجتازة" + (" (مرتّبة بقرب ما رُئي من المقصود)" if reach else "") + ":",
           *[f"- {iid}" + (f" [{reach[iid]:.2f}]" if iid in reach else "") + f": {seen.get(iid, '')}" for iid in m.get("allowed") or []]]
    if m.get("blocked"):
        out += ["المردودة (لا يُبنى عليها مفهوم؛ الأداة تردّه):", *[f"- {iid}: {why}" for iid, why in m["blocked"].items()]]
    if m.get("weak"):
        out += ["تنبيه: لم تجتز خمس أفكار بعد الجولات المسموحة، فهذه مقروءة قراءة خاطئة ولا تُمنع؛ غيّر هيئتها جذريًا إن بنيتَ عليها:",
                *[f"- {iid}: {why}" for iid, why in m["weak"].items()]]
    return [*out, ""]


def judge_lines(ws: Workspace) -> list[str]:
    """قسم طلب التحكيم: ما اجتاز القراءة العمياء من الأفكار وما رُدّ. الحَكَم لم يكن يُعطاه، فأوصى ببدائل مردودة واخترع
    الرسّام بعدها أفكارًا بلا مصغّرة تتجاوز البوابة (سِمة v2)."""
    m = ws.read_marker(KIND)
    if not m:
        return []
    out = ["## أفكار المصغّرات عند القارئ الأعمى",
           "قبل الرسم قرأ قارئ مستقل مصغّرة كل فكرة في `work/ideas.yaml`. إن رأيتَ استبدال فكرة مفهوم (`replace: true`) فلا تسمِّ في",
           "`direction` بديلًا من المردودة ولا فكرة من خارج الملف: البديل يختاره الرسّام من المجتازة وحدها.",
           "المجتازة: " + ("، ".join(m.get("allowed") or []) or "لا شيء")]
    if m.get("blocked"):
        out += ["المردودة (لا يُبنى عليها مفهوم):", *[f"- {iid}: {why}" for iid, why in m["blocked"].items()]]
    if m.get("weak"):
        out += ["مقروءة قراءة خاطئة ولم تُمنع لاستنفاد الجولات:", *[f"- {iid}: {why}" for iid, why in m["weak"].items()]]
    return [*out, ""]


def concept_problems(ws: Workspace) -> list[str]:
    """مفهوم مبني على فكرة ردّها القارئ الأعمى مشكلة تباعد: يُعاد رسمه من فكرة مجتازة. ملف غير صالح يُترك لفحصه الأصلي."""
    blocked = ws.read_marker(KIND).get("blocked") or {}
    if not blocked:
        return []
    try:
        concepts = read_concepts(ws)
    except ValueError:  # صيغة لا تُقرأ (protocol.FormatError)
        return []
    return [f"المفهوم {c.id} مبني على الفكرة {c.idea_id} التي ردّها القارئ الأعمى ({blocked[c.idea_id]}): ابنِه على فكرة مجتازة"
            for c in concepts if c.idea_id in blocked]


def archive(ws: Workspace, hist: Path, tag: str) -> None:
    """مع أرشفة المفاهيم: المصغّرات وقراءاتها تخص دورة رسم واحدة، والدورة التالية تبدأ بأفكار ومصغّرات جديدة."""
    d = thumbs_dir(ws)
    if d.is_dir():
        live_preview.clear(d)
        dst = hist / KIND
        for p in sorted(d.iterdir()):
            if p.is_file():
                dst.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), dst / p.name)
    shutil.rmtree(ws.render_dir / KIND, ignore_errors=True)
    blind.archive(ws, tag, KIND)
    if ws.done(KIND):
        ws.marker(KIND).unlink()
