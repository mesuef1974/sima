"""جِدّة الأفكار: لا يعود الرسّام إلى فكرة رفضها المالك، لا بنصّها ولا بصياغة أخرى لها.

المرفوض مصدران: مجموعات المفاهيم المؤرشفة في `work/history/` (جولات تركها المالك)، وسجل `work/history/rejected.jsonl` الذي
يحفظ فكرة كل مفهوم رفضه المالك قبل أن يُعاد الرسم فوقها. الطلبات تسرد المرفوض صريحًا، والفحص يقيس قرب كل مفهوم جديد منه
بنموذج تضمين محلي (منفذ Embedder) ويردّ ما بلغ العتبة. القياس على نص الفكرة لا على شكلها: يكشف عودة المجاز لا تشابه الرسم.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass

import yaml

from .. import config
from ..domain import Concept
from .ports import Embedder
from .workspace import Workspace

ARCHIVES = ("medium-", "style-")
SEP = "\x1f"


@dataclass(frozen=True)
class Rejected:
    name: str
    sentence: str
    source: str


def log_path(ws: Workspace):
    return ws.work / "history" / "rejected.jsonl"


def text(name: str, sentence: str) -> str:
    return f"{name.strip()}. {sentence.strip()}"


def _key(name: str) -> str:
    """مفتاح تجميع الاسم: بلا تشكيل ولا «ال» التعريف، فـ«الميسم» و«ميسم» فكرة واحدة."""
    s = "".join(ch for ch in unicodedata.normalize("NFD", name) if not unicodedata.combining(ch))
    return " ".join(re.sub(r"^ال", "", w) for w in s.split())


def record(ws: Workspace, concept: Concept, reason: str, at: str) -> bool:
    """يحفظ فكرة مفهوم رفضه المالك قبل أن يُعاد رسمه فوقها. idempotent بمفتاح (المعرّف، وقت القرار)."""
    p = log_path(ws)
    rows = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()] if p.is_file() else []
    if any(r.get("id") == concept.id and r.get("at") == at for r in rows):
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {"id": concept.id, "at": at, "name": concept.name, "sentence": concept.sentence, "reason": reason}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True


def rejected(ws: Workspace) -> list[Rejected]:
    """كل ما رُفض بترتيب زمني تقريبي (الأرشيف ثم السجل)، بلا تكرار للنص نفسه."""
    out: dict[str, Rejected] = {}
    hist = ws.work / "history"
    for d in sorted(p for p in hist.iterdir() if p.is_dir() and p.name.startswith(ARCHIVES)) if hist.is_dir() else []:
        f = d / "concepts.yaml"
        try:
            rows = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("concepts", []) if f.is_file() else []
        except (yaml.YAMLError, AttributeError):
            rows = []
        for c in rows if isinstance(rows, list) else []:
            if isinstance(c, dict) and str(c.get("sentence") or "").strip():
                r = Rejected(str(c.get("name") or c.get("id") or ""), str(c["sentence"]), d.name)
                out.setdefault(text(r.name, r.sentence), r)
    p = log_path(ws)
    for ln in p.read_text(encoding="utf-8").splitlines() if p.is_file() else []:
        if ln.strip():
            row = json.loads(ln)
            r = Rejected(str(row.get("name") or ""), str(row.get("sentence") or ""), "رفض المالك " + str(row.get("at") or "")[:10])
            if r.sentence.strip():
                out.setdefault(text(r.name, r.sentence), r)
    return list(out.values())


def lines(ws: Workspace) -> list[str]:
    """قسم الطلب: الأفكار المرفوضة مجمّعة بالاسم (الأحدث صياغةً وعدد مرات العودة إليها)."""
    groups: dict[str, list[Rejected]] = {}
    for r in rejected(ws):
        groups.setdefault(_key(r.name), []).append(r)
    if not groups:
        return []
    rows = sorted(groups.values(), key=len, reverse=True)[:config.NOVELTY_LIST_MAX]
    return ["## أفكار رفضها المالك (لا تعد إليها ولا إلى صياغة أخرى لها)",
            *[f"- «{g[-1].name}»{f' (رُسمت {len(g)} مرات)' if len(g) > 1 else ''}: {g[-1].sentence.strip()[:160]}" for g in rows],
            "المجازات المتكررة أعلاه استُنفدت. ابحث عن الحيلة في منطقة معنى أخرى من الاسم والموجز، لا في تنويع جديد عليها.",
            "وإن ورد أحد هذه المجازات في نص الموجز نفسه فالمرفوض صورته المرسومة لا معناه: خذ المعنى وجسّده بصورة أخرى.",
            f"الأداة تقيس قرب نص كل مفهوم جديد من هذه القائمة وتردّ ما بلغ تشابهه {config.NOVELTY_MAX_SIM:g}.", ""]


def cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb) if na and nb else 0.0


def check(ws: Workspace, concepts: list[Concept], embedder: Embedder | None, skip: set[str] | None = None) -> list[str]:
    """مشاكل الجِدّة للمفاهيم الحالية. النتيجة تُحفظ ببصمة النصوص فلا يُعاد الاستدعاء لمحتوى لم يتغيّر. خادم التضمين
    المتوقف لا يوقف الخط: يُتجاوز الفحص ولا تُحفظ نتيجة، فيُعاد حين يعود. skip: مفاهيم رفضها المالك ولم يُعَد رسمها
    بعد؛ طلب إعادة رسمها قائم، فلا تُحاسَب على مطابقة فكرتها المسجّلة للتوّ."""
    concepts = [c for c in concepts if c.id not in (skip or set())]
    old = rejected(ws)
    if embedder is None or not old or not concepts:
        return []
    cur = [text(c.name, c.sentence) for c in concepts]
    past = [text(r.name, r.sentence) for r in old]
    model = str(getattr(embedder, "model", ""))
    digest = hashlib.sha256(SEP.join([model, f"{config.NOVELTY_MAX_SIM:g}", *cur, "|", *past]).encode("utf-8")).hexdigest()[:16]
    mk = ws.read_marker("novelty")
    if mk.get("digest") == digest:
        return list(mk.get("problems", []))
    vecs = embedder.embed(cur + past)
    if vecs is None:
        return []
    prev = mk.get("tries", {})
    problems, nearest, tries, waived = [], {}, {}, []
    for i, c in enumerate(concepts):
        sim, j = max((cosine(vecs[i], vecs[len(cur) + k]), k) for k in range(len(past)))
        nearest[c.id] = {"sim": round(sim, 3), "name": old[j].name, "source": old[j].source}
        if sim < config.NOVELTY_MAX_SIM:
            continue
        tries[c.id] = n = int(prev.get(c.id, 0)) + 1
        if n > config.NOVELTY_MAX_TRIES:  # كل ردّ استدعاء رسم كامل؛ بعد المحاولتين يُقبل الأقرب ويحكم عليه الحَكَم
            waived.append(c.id)
            continue
        problems.append(f"المفهوم {c.id} «{c.name}» يعود إلى فكرة رفضها المالك: «{old[j].name}» ({old[j].source}، تشابه النص "
                        f"{sim:.2f} والحد {config.NOVELTY_MAX_SIM:g}). استبدله بفكرة من منطقة معنى أخرى، لا بإعادة صياغتها.")
    ws.mark_done("novelty", {"digest": digest, "model": model, "problems": problems, "nearest": nearest, "tries": tries, "waived": waived})
    return problems
