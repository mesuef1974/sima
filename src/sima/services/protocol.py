"""بروتوكول الملفات بين الأداة والنموذج: الأفكار والمفاهيم ونقد الجولات.

النموذج (جلسة Claude بمهارة sima-design) يكتب هذه الملفات؛ الأداة تقرأها وتتحقق منها.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .. import config
from ..domain import Concept, Family, Idea, Medium, missing_families
from .workspace import Workspace


@dataclass
class Validation:
    ok: bool
    problems: list[str] = field(default_factory=list)


class FormatError(ValueError):
    """ملف كتبه النموذج بصيغة لا تُقرأ. رسالته مشاكل الصيغة بنصّها، وتُكتب في الطلب العائد إليه."""


FAMILY_VALUES = "، ".join(f.value for f in Family)
MEDIUM_VALUES = "، ".join(m.value for m in Medium)
CRITIQUE_ACTIONS = ("keep", "revise", "drop")


def _shape(value) -> str:
    return {dict: "خريطة", list: "قائمة", str: "نص"}.get(type(value), type(value).__name__)


def _rows(path: Path, key: str) -> tuple[list, list[str]]:
    """بنود ملف YAML كتبه النموذج، وما لا يُقرأ من شكله. القارئ الوحيد لملفَي الأفكار والمفاهيم: لا يرمي استثناءً، وكل
    خلل (YAML معطوب، قائمة في المستوى الأعلى، بند ليس خريطة) مشكلة بنصّها. كان الالتقاط `YAMLError, KeyError, ValueError`
    وحده، فأسقط `AttributeError` و`TypeError` الخط بعد استدعاء مدفوع بدل أن يعود الخلل إلى النموذج."""
    name = f"work/{path.name}"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        return [], [f"{name}: YAML غير صالح: {exc}"]
    if data is None:
        return [], []
    if not isinstance(data, dict):
        return [], [f"{name}: المستوى الأعلى يجب أن يكون خريطة فيها `{key}:` لا {_shape(data)}"]
    rows = data.get(key)
    if rows is None:
        return [], []
    if not isinstance(rows, list):
        return [], [f"{name}: `{key}` يجب أن يكون قائمة بنود لا {_shape(rows)}"]
    return rows, []


def _fields(d, n: int, name: str, what: str, required: tuple[str, ...]) -> tuple[str, list[str]]:
    """وسم البند وما ينقصه: (وسم، مشاكل). بند ليس خريطة أو ينقصه حقل إلزامي مشكلة باسمه."""
    if not isinstance(d, dict):
        return "", [f"{name}: البند {n} ليس خريطة حقول بل {_shape(d)}"]
    tag = f"{name}: {what} {d['id']}" if d.get("id") not in (None, "") else f"{name}: البند {n}"
    missing = [k for k in required if d.get(k) in (None, "")]
    return tag, [f"{tag}: ينقصه {'، '.join(missing)}"] if missing else []


def parse_ideas(ws: Workspace) -> tuple[list[Idea], list[str]]:
    """الأفكار المقروءة ومشاكل صيغة ملفها، كل مشكلة باسم بندها وبالقيم المقبولة (فيُصحَّح البند وحده)."""
    p = ws.work / "ideas.yaml"
    if not p.is_file():
        return [], []
    rows, problems = _rows(p, "ideas")
    out: list[Idea] = []
    for n, d in enumerate(rows, 1):
        tag, bad = _fields(d, n, "work/ideas.yaml", "الفكرة", ("id", "family", "sentence"))
        if not bad and str(d["family"]) not in set(Family):
            bad = [f"{tag}: family «{d['family']}» ليست من القيم المقبولة ({FAMILY_VALUES})"]
        if bad:
            problems += bad
            continue
        out.append(Idea(id=str(d["id"]), family=Family(str(d["family"])), sentence=str(d["sentence"]), twist=str(d.get("twist") or "")))
    return out, problems


def parse_concepts(ws: Workspace) -> tuple[list[Concept], list[str]]:
    """المفاهيم المقروءة ومشاكل صيغة ملفها، بالطريقة نفسها."""
    p = ws.work / "concepts.yaml"
    if not p.is_file():
        return [], []
    rows, problems = _rows(p, "concepts")
    out: list[Concept] = []
    for n, d in enumerate(rows, 1):
        tag, bad = _fields(d, n, "work/concepts.yaml", "المفهوم", ("id", "family"))
        if not bad and str(d["family"]) not in set(Family):
            bad = [f"{tag}: family «{d['family']}» ليست من القيم المقبولة ({FAMILY_VALUES})"]
        if not bad and str(d.get("medium") or "abstract_mark") not in set(Medium):
            bad = [f"{tag}: medium «{d['medium']}» ليس من القيم المقبولة ({MEDIUM_VALUES})"]
        if bad:
            problems += bad
            continue
        out.append(Concept(
            id=str(d["id"]), name=str(d.get("name") or d["id"]), family=Family(str(d["family"])),
            medium=Medium(str(d.get("medium") or "abstract_mark")), sentence=str(d.get("sentence") or ""),
            idea_id=(str(d["idea_id"]) if d.get("idea_id") is not None else None),
            construction=str(d.get("construction") or ""), reference=str(d.get("reference") or ""),
        ))
    return out, problems


def format_problems(ws: Workspace) -> list[str]:
    """ما لا يُقرأ من صيغة ملفَي الأفكار والمفاهيم (لا ما ينقص محتواهما): يُصحَّح بطلب ضيّق لا بإعادة الطلب الإبداعي."""
    return [*parse_ideas(ws)[1], *parse_concepts(ws)[1]]


def read_ideas(ws: Workspace) -> list[Idea]:
    """الأفكار، أو FormatError بمشاكل الصيغة (من يعرض فقط يلتقطها؛ الخط يسأل `parse_ideas`)."""
    ideas, problems = parse_ideas(ws)
    if problems:
        raise FormatError("؛ ".join(problems))
    return ideas


def read_concepts(ws: Workspace) -> list[Concept]:
    concepts, problems = parse_concepts(ws)
    if problems:
        raise FormatError("؛ ".join(problems))
    return concepts


def concept_svg_path(ws: Workspace, concept_id: str) -> Path:
    return ws.concepts_dir / f"{concept_id}.svg"


def read_concept_svgs(ws: Workspace, concepts: list[Concept]) -> dict[str, str]:
    out = {}
    for c in concepts:
        p = concept_svg_path(ws, c.id)
        if p.is_file():
            out[c.id] = p.read_text(encoding="utf-8")
    return out


def small_svg_path(ws: Workspace, concept_id: str) -> Path:
    return ws.concepts_dir / f"{concept_id}.small.svg"


def read_small_svgs(ws: Workspace, concepts: list[Concept]) -> dict[str, str]:
    out = {}
    for c in concepts:
        p = small_svg_path(ws, c.id)
        if p.is_file():
            out[c.id] = p.read_text(encoding="utf-8")
    return out


def merged_digest(svgs: dict[str, str], smalls: dict[str, str]) -> str:
    return svgs_digest({**svgs, **{k + ".small": v for k, v in smalls.items()}})


def concepts_digest(ws: Workspace) -> str:
    """بصمة ما يُعرض في بوابة المفاهيم: ملف المفاهيم وكل رسومها. أي تعديل من النموذج بعد العرض يغيّرها. يكتبها الخط في
    نتيجته حين يقف عند المالك، ويقارنها الوارد بما على القرص."""
    h = hashlib.sha256()
    svgs = sorted(ws.concepts_dir.glob("*.svg")) if ws.concepts_dir.is_dir() else []
    for p in (ws.work / "concepts.yaml", *svgs):
        h.update(p.name.encode("utf-8"))
        h.update(p.read_bytes() if p.is_file() else b"<missing>")
    return h.hexdigest()[:16]


def svgs_digest(svgs: dict[str, str]) -> str:
    h = hashlib.sha256()
    for k in sorted(svgs):
        h.update(k.encode("utf-8"))
        h.update(svgs[k].encode("utf-8"))
    return h.hexdigest()[:16]


def mark_spec_path(ws: Workspace, svg_id: str) -> Path:
    return ws.concepts_dir / f"{svg_id}.mark.yaml"


def compile_marks(ws: Workspace, build) -> dict[str, str]:
    """يحوّل كل work/concepts/<id>.mark.yaml (و<id>.small.mark.yaml) إلى <id>.svg بأداة البناء. idempotent: لا يكتب إلا
    ما تغيّر. خطأ البناء يُكتب في <id>.mark.error.txt ويُحذف SVG القديم كي لا يُحكم على رسم لا يطابق وصفه. يعيد الأخطاء."""
    if not ws.concepts_dir.is_dir():
        return {}
    try:
        names = {c.id: c.name for c in read_concepts(ws)}
    except FormatError:
        names = {}
    return compile_dir(ws.concepts_dir, build, names)


def compile_one(spec: Path, build, names: dict[str, str] | None = None) -> tuple[str | None, str | None]:
    """يبني <id>.mark.yaml واحدًا إلى <id>.svg بجانبه. يعيد (svg, None) أو (None, الخطأ). خطأ البناء يُكتب في
    <id>.mark.error.txt ويُحذف SVG القديم كي لا يُحكم على رسم لا يطابق وصفه."""
    folder, sid = spec.parent, spec.name.removesuffix(".mark.yaml")
    out, err = folder / f"{sid}.svg", folder / f"{sid}.mark.error.txt"
    base = sid.removesuffix(".small")
    try:
        svg = build(spec.read_text(encoding="utf-8"), (names or {}).get(base, base) + (" (مصغّر)" if sid != base else ""))
    except Exception as exc:  # noqa: BLE001 — أي فشل في البناء رسالة للرسّام لا انهيار للخط
        err.write_text(str(exc), encoding="utf-8")
        out.unlink(missing_ok=True)
        return None, str(exc)
    err.unlink(missing_ok=True)
    if not out.is_file() or out.read_text(encoding="utf-8") != svg:
        out.write_text(svg, encoding="utf-8")
    return svg, None


def compile_dir(folder: Path, build, names: dict[str, str]) -> dict[str, str]:
    """يبني كل <id>.mark.yaml في المجلد إلى <id>.svg (المفاهيم وعينات الطابع). idempotent. يعيد الأخطاء."""
    errors: dict[str, str] = {}
    for spec in sorted(folder.glob("*.mark.yaml")):
        _, e = compile_one(spec, build, names)
        if e is not None:
            errors[spec.name.removesuffix(".mark.yaml")] = e
    return errors


def font_family(font: str) -> str:
    """اسم عائلة الخط من اسم ملفه: `ReemKufi[wght].ttf` وReemKufi-Bold.ttf عائلة واحدة."""
    return re.split(r"[\[\-.]", Path(str(font)).name, maxsplit=1)[0]


def font_bases(spec_text: str) -> set[str]:
    """عائلات الخطوط التي يُبنى عليها الوصف (أشكال text). وصف غير صالح أو مبني من الصفر: مجموعة فارغة."""
    try:
        data = yaml.safe_load(spec_text)
    except yaml.YAMLError:
        return set()
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            if "text" in node and node.get("font"):
                found.add(font_family(node["font"]))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return found


def shared_font_problems(ws: Workspace, concepts: list[Concept]) -> list[str]:
    """أكثر من FONT_BASE_MAX مفاهيم على خط واحد مشكلة: القاعدة المشتركة تجعلها تنويعات لا مفاهيم متباعدة."""
    users: dict[str, list[str]] = {}
    for c in concepts:
        spec = mark_spec_path(ws, c.id)
        for fam in sorted(font_bases(spec.read_text(encoding="utf-8"))) if spec.is_file() else []:
            users.setdefault(fam, []).append(c.id)
    return [f"قاعدة خط واحدة لأكثر من {config.FONT_BASE_MAX} مفاهيم: {fam} في {'، '.join(ids)}. أبقِ {config.FONT_BASE_MAX} عليه وابنِ"
            " الباقي على خط آخر من fonts/ أو من الصفر على شبكة، بمنطق شكلي مختلف لا بتبديل الخط وحده."
            for fam, ids in sorted(users.items()) if len(ids) > config.FONT_BASE_MAX]


def ideas_problems(ws: Workspace) -> tuple[list[Idea], list[str]]:
    """الأفكار وما ينقص ملفها: يشترك فيه فحص الرسم وفحص المصغّرات (services/thumbs.py)."""
    ideas, problems = parse_ideas(ws)
    if problems:
        return [], problems
    if not ideas:
        problems.append("work/ideas.yaml مفقود أو فارغ")
    elif not (config.IDEAS_MIN <= len(ideas) <= config.IDEAS_MAX):
        problems.append(f"عدد الأفكار {len(ideas)}؛ المطلوب بين {config.IDEAS_MIN} و{config.IDEAS_MAX}")
    elif sum(1 for i in ideas if i.twist.strip()) < config.IDEAS_MIN:
        problems.append(f"الأفكار بلا حيلة (twist): المطلوب {config.IDEAS_MIN} فكرة على الأقل لكل منها twist")
    return ideas, problems


def validate_diverge(ws: Workspace, medium: Medium, *, construct: bool = False) -> Validation:
    _ideas, problems = ideas_problems(ws)
    concepts, bad = parse_concepts(ws)
    problems += bad
    if not bad and not concepts:
        problems.append("work/concepts.yaml مفقود أو فارغ")
    elif not bad:  # صيغة لا تُقرأ: مشاكلها تكفي، ولا يُفحص محتوى مقروء نصفه
        if len(concepts) != config.CONCEPTS_REQUIRED:
            problems.append(f"عدد المفاهيم {len(concepts)}؛ المطلوب {config.CONCEPTS_REQUIRED} بالضبط")
        miss = missing_families(concepts)
        if miss:
            problems.append("عائلات ناقصة: " + ", ".join(f.value for f in miss))
        ids = [c.id for c in concepts]
        if len(set(ids)) != len(ids):
            problems.append("معرّفات مكررة في concepts.yaml")
        wrong = [c.id for c in concepts if c.medium is not medium]
        if wrong:
            problems.append(f"مفاهيم بوسيط غير الوسيط الحالي ({medium.value}): " + ", ".join(wrong))
        for c in concepts:
            for sid in (c.id, c.id + ".small"):
                e = ws.concepts_dir / f"{sid}.mark.error.txt"
                if e.is_file():
                    problems.append(f"خطأ في بناء work/concepts/{sid}.mark.yaml: {e.read_text(encoding='utf-8')}")
            built = construct and medium.value in config.CONSTRUCT_REQUIRED
            if built and not mark_spec_path(ws, c.id).is_file():
                problems.append(f"البناء مفقود: work/concepts/{c.id}.mark.yaml (اكتب البناء لا SVG؛ الأداة تولّد SVG منه)")
            if built and medium.value in config.SMALL_REQUIRED and not mark_spec_path(ws, c.id + ".small").is_file():
                problems.append(f"بناء الرمز المصغّر مفقود: work/concepts/{c.id}.small.mark.yaml (يُبنى كالمفهوم، لا SVG يدوي)")
            if not concept_svg_path(ws, c.id).is_file():
                problems.append(f"ملف SVG مفقود: work/concepts/{c.id}.svg")
            if medium.value in config.SMALL_REQUIRED and not small_svg_path(ws, c.id).is_file():
                problems.append(f"الرمز المصغّر مفقود: work/concepts/{c.id}.small.svg (إلزامي لوسيط {medium.value})")
            if not c.sentence.strip():
                problems.append(f"المفهوم {c.id} بلا جملة فكرة")
            if c.family is Family.SYMBOLIC and not c.reference.strip():
                problems.append(f"المفهوم الرمزي {c.id} بلا مرجع تاريخي موثّق")
    return Validation(ok=not problems, problems=problems)


def read_critique(ws: Workspace, n: int) -> tuple[dict[str, dict], list[str]] | None:
    """أحكام جولة النقد ومشاكل صيغة ملفها: (verdicts، مشاكل)، أو None إن لم تُكتب الجولة. قائمة في المستوى الأعلى أو
    `c1: keep` كانت تُسقط الخط بـ`AttributeError`؛ الآن مشكلة تُكتب في طلب الجولة نفسه."""
    p = ws.critique_dir / f"round{n}.yaml"
    if not p.is_file():
        return None
    name = f"work/critique/{p.name}"
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        return {}, [f"{name}: YAML غير صالح: {exc}"]
    if data is None:
        return {}, []
    verdicts = data.get("verdicts", {}) if isinstance(data, dict) else None
    verdicts = {} if verdicts is None and isinstance(data, dict) else verdicts  # بلا أحكام: لا تعديل مطلوب (كما كان)
    if not isinstance(verdicts, dict):
        return {}, [f"{name}: المطلوب خريطة فيها `verdicts:` ولكل معرّف مدخله {{action, score, notes, changes}}"]
    problems = []
    for cid, v in verdicts.items():
        if not isinstance(v, dict):
            problems.append(f"{name}: حكم {cid} ليس خريطة {{action: ...}} بل {_shape(v)}")
        elif v.get("action") not in CRITIQUE_ACTIONS:
            problems.append(f"{name}: {cid}: action «{v.get('action')}» ليست من {'، '.join(CRITIQUE_ACTIONS)}")
    return ({} if problems else {str(k): v for k, v in verdicts.items()}), problems


def write_critique_request(ws: Workspace, n: int, digest: str) -> None:
    ws.critique_dir.mkdir(parents=True, exist_ok=True)
    p = ws.critique_dir / f"round{n}.request.json"
    if not p.is_file():
        p.write_text(json.dumps({"round": n, "digest": digest}, ensure_ascii=False), encoding="utf-8")


def read_critique_request(ws: Workspace, n: int) -> dict:
    p = ws.critique_dir / f"round{n}.request.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def critique_rounds_done(ws: Workspace) -> int:
    n = 0
    while (ws.critique_dir / f"round{n + 1}.yaml").is_file():
        n += 1
    return n


def archive_svg(ws: Workspace, concept_id: str, round_n: int) -> None:
    src = concept_svg_path(ws, concept_id)
    if not src.is_file():
        return
    hist = ws.work / "history"
    hist.mkdir(parents=True, exist_ok=True)
    dst = hist / f"{concept_id}.r{round_n}.svg"
    if not dst.is_file():
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
