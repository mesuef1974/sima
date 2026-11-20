"""الحَكَم المستقل: بروتوكول ملفات التحكيم وحساب عتبة الاحتراف.

الحَكَم استدعاء نموذج منفصل لم يرسم المفاهيم، وكتابته محصورة في work/judge/ (لا يلمس SVG). يكتب الدرجات فقط؛
العتبة والاجتياز والترتيب تحسبها هذه الخدمة حتميًا، فلا يجيز الحَكَم شيئًا بقوله. المعيار في
`.claude/skills/sima-design/references/40-professional-bar.md`.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field

import yaml

from .. import config
from .workspace import Workspace


@dataclass(frozen=True)
class Score:
    concept_id: str
    scores: dict[str, int]
    blockers: tuple[str, ...] = ()
    direction: str = ""
    replace: bool = False

    @property
    def total(self) -> int:
        return sum(self.scores.values())

    @property
    def passed(self) -> bool:
        return (self.total >= config.JUDGE_MIN_TOTAL
                and all(v >= config.JUDGE_MIN_EACH for v in self.scores.values())
                and all(self.scores.get(k, 0) >= m for k, m in config.JUDGE_KEY_MIN.items()))

    def failures(self) -> list[str]:
        out = []
        if self.total < config.JUDGE_MIN_TOTAL:
            out.append(f"المجموع {self.total} دون {config.JUDGE_MIN_TOTAL}")
        out += [f"{k}={v} دون {config.JUDGE_MIN_EACH}" for k, v in self.scores.items() if v < config.JUDGE_MIN_EACH]
        out += [f"{k}={self.scores.get(k, 0)} دون {m}" for k, m in config.JUDGE_KEY_MIN.items()
                if config.JUDGE_MIN_EACH <= self.scores.get(k, 0) < m]
        return out


@dataclass
class Judgement:
    digest: str
    scores: dict[str, Score] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def judge_dir(ws: Workspace):
    return ws.work / "judge"


def judge_path(ws: Workspace, digest: str):
    return judge_dir(ws) / f"{digest}.yaml"


def rounds(ws: Workspace) -> int:
    """جولات التحكيم في الدورة الحالية (تُؤرشف عند كل ملاحظة من المالك أو تبديل وسيط)."""
    d = judge_dir(ws)
    return len(list(d.glob("*.yaml"))) if d.is_dir() else 0


def read(ws: Workspace, digest: str, ids: list[str]) -> Judgement | None:
    """None إن لم يُحكم على هذا المحتوى بعد. ملف ناقص أو درجات خارج 0-5 تعود مشاكل، فيُعاد الطلب."""
    p = judge_path(ws, digest)
    if not p.is_file():
        return None
    j = Judgement(digest=digest)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        j.problems.append(f"ملف التحكيم غير صالح: {exc}")
        return j
    verdicts = data.get("verdicts") if isinstance(data, dict) else None
    if not isinstance(verdicts, dict):  # قائمة في المستوى الأعلى أو verdicts ليست خريطة: مشكلة تعود في الطلب لا انهيار
        j.problems.append("ملف التحكيم ليس بالصيغة المطلوبة: خريطة فيها `verdicts:` ولكل معرّف مدخله")
        return j
    for cid in ids:
        v = verdicts.get(cid)
        if not isinstance(v, dict):
            j.problems.append(f"لا حكم للمفهوم {cid}")
            continue
        raw = v.get("scores") if isinstance(v.get("scores"), dict) else {}
        scores: dict[str, int] = {}
        for k in config.JUDGE_CRITERIA:
            try:
                n = int(raw.get(k))
            except (TypeError, ValueError):
                j.problems.append(f"{cid}: درجة {k} مفقودة")
                continue
            if not 0 <= n <= 5:
                j.problems.append(f"{cid}: درجة {k}={n} خارج 0-5")
                continue
            scores[k] = n
        if len(scores) == len(config.JUDGE_CRITERIA):
            blockers = v.get("blockers") or []
            j.scores[cid] = Score(cid, scores, tuple(str(b) for b in (blockers if isinstance(blockers, list) else [blockers])),
                                  str(v.get("direction") or ""), bool(v.get("replace")))
    return j


def shortlist(j: Judgement, eligible: list[str], n: int | None = None) -> tuple[list[str], bool]:
    """أفضل n مجتازين بالمجموع (ثم بالمعرّف للحتمية). إن لم يكفِ المجتازون يُكمَّل بالأعلى درجة ويُعاد below=True."""
    n = n or config.SHORTLIST
    ranked = sorted((s for cid, s in j.scores.items() if cid in eligible), key=lambda s: (-s.total, s.concept_id))
    passed = [s.concept_id for s in ranked if s.passed]
    if len(passed) >= n:
        return passed[:n], False
    rest = [s.concept_id for s in ranked if not s.passed]
    return (passed + rest)[:n], True


def archive(ws: Workspace, tag: str) -> None:
    d = judge_dir(ws)
    if not d.is_dir() or not any(d.glob("*.yaml")):
        return
    hist = ws.work / "history"
    k = 1
    while (hist / f"judge-{tag}-{k}").exists():
        k += 1
    dst = hist / f"judge-{tag}-{k}"
    dst.mkdir(parents=True)
    for p in d.glob("*.yaml"):
        shutil.move(str(p), dst / p.name)
