"""القراءة العمياء: قارئ مستقل يرى صور المفاهيم وحدها ويكتب ما يراه قبل أن يصل شيء إلى الحَكَم.

القارئ استدعاء نموذج ثالث (غير الرسّام وغير الحَكَم) لا يُعطى اسم العلامة ولا فكرتها ولا الموجز، وقراءته محصورة في صور
work/render/ وكتابته في work/blind/. يصنّف ما يقرؤه (حرف أجنبي، رمز شائع، أيقونة واجهة، علامة معروفة...) وقوة القراءة؛
والردّ يحسبه هذا الملف حتميًا: القارئ لا يجيز ولا يردّ بقوله. سبب وجودها: في سِمة v2 كان أول عيب في خمسة عشر حكمًا
متتاليًا قراءة خاطئة (ä، ö، σ، @، مؤشّر تحميل) توقّعها الرسّام نفسه وسلّم مع ذلك، فاستُهلكت جولات الحَكَم الثلاث فيها.
"""
from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .. import config
from .workspace import Workspace

KIND_AR = {
    "arabic": "حرف أو كلمة عربية", "foreign_letter": "حرف غير عربي", "common_symbol": "رمز شائع", "ui_icon": "أيقونة واجهة",
    "brand": "علامة تجارية معروفة", "object": "شيء من العالم", "none": "شكل مجرد",
}
BLOCKING = ("foreign_letter", "common_symbol", "ui_icon", "brand")  # قراءة تزاحم العلامة؛ العربي والشيء والمجرد يحكم فيها الحَكَم
REQUEST = "REQUEST-blind.md"


@dataclass(frozen=True)
class Reading:
    concept_id: str
    seen: str
    reads_as: str
    kind: str
    strength: int

    @property
    def blocked(self) -> bool:
        return self.kind in BLOCKING and self.strength >= config.BLIND_BLOCK

    def line(self) -> str:
        what = f"يُقرأ {KIND_AR[self.kind]}" + (f" «{self.reads_as}»" if self.reads_as else "")
        return f"رأى «{self.seen}»؛ {what} بقوة {self.strength} من 3"


@dataclass
class Readings:
    digest: str
    readings: dict[str, Reading] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def blocked(self) -> list[Reading]:
        return [r for r in self.readings.values() if r.blocked]


def blind_dir(ws: Workspace, kind: str = ""):
    """قراءات المفاهيم في work/blind/، وقراءات نوع آخر (مصغّرات الأفكار) في مجلد فرعي باسمه فلا يُحسب أحدهما على الآخر."""
    return ws.work / "blind" / kind if kind else ws.work / "blind"


def path(ws: Workspace, digest: str, kind: str = ""):
    return blind_dir(ws, kind) / f"{digest}.yaml"


def rounds(ws: Workspace, kind: str = "") -> int:
    """قراءات الدورة الحالية (تُؤرشف مع أحكام الحَكَم عند كل ملاحظة من المالك أو رسم جديد)."""
    d = blind_dir(ws, kind)
    return len(list(d.glob("*.yaml"))) if d.is_dir() else 0


def read(ws: Workspace, digest: str, ids: list[str], kind: str = "") -> Readings | None:
    """None إن لم يُقرأ هذا المحتوى بعد. ملف ناقص أو تصنيف مجهول يعود مشاكل، فيُعاد الطلب."""
    p = path(ws, digest, kind)
    if not p.is_file():
        return None
    out = Readings(digest=digest)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        out.problems.append(f"ملف القراءة غير صالح: {exc}")
        return out
    rows = data.get("readings") if isinstance(data, dict) else None
    rows = rows if isinstance(rows, dict) else {}
    for cid in ids:
        v = rows.get(cid)
        if not isinstance(v, dict):
            out.problems.append(f"لا قراءة للمفهوم {cid}")
            continue
        seen, kind = str(v.get("seen") or "").strip(), str(v.get("kind") or "").strip()
        try:
            strength = int(v.get("strength"))
        except (TypeError, ValueError):
            out.problems.append(f"{cid}: strength مفقودة")
            continue
        if not seen:
            out.problems.append(f"{cid}: seen فارغة")
        elif kind not in KIND_AR:
            out.problems.append(f"{cid}: kind «{kind}» ليس من {'، '.join(KIND_AR)}")
        elif not 0 <= strength <= 3:
            out.problems.append(f"{cid}: strength={strength} خارج 0-3")
        else:
            out.readings[cid] = Reading(cid, seen, str(v.get("reads_as") or "").strip(), kind, strength)
    return out


def archive(ws: Workspace, tag: str, kind: str = "") -> None:
    d = blind_dir(ws, kind)
    if not d.is_dir() or not any(d.glob("*.yaml")):
        return
    hist = ws.work / "history"
    stem = f"blind-{kind}-{tag}" if kind else f"blind-{tag}"
    k = 1
    while (hist / f"{stem}-{k}").exists():
        k += 1
    dst = hist / f"{stem}-{k}"
    dst.mkdir(parents=True)
    for p in d.glob("*.yaml"):
        shutil.move(str(p), dst / p.name)


def write_request(ws: Workspace, ids: list[str], digest: str, problems: list[str], *, kind: str = "", name: str = REQUEST,
                  images: Callable[[str], list[Path]] | None = None) -> None:
    """طلب بلا اسم ولا فكرة ولا موجز: المعرّفات والصور وحدها، كي تبقى القراءة عمياء فعلًا. images يعيد صور كل معرّف
    (الافتراضي صور تصيير المفهوم 256 و16 والمطموسة)."""
    kinds = "|".join(KIND_AR)
    target = f"work/blind/{kind + '/' if kind else ''}{digest}.yaml"
    shots = images or (lambda cid: [ws.render_dir / cid / f"{n}.png" for n in ("256", "16", "blurred")])
    lines = [
        "# طلب القراءة العمياء", "",
        "أنت قارئ مستقل. لا تعرف اسم العلامة ولا فكرتها ولا من رسمها، ولا تبحث عن ذلك: لا تقرأ أي ملف غير الصور أدناه.",
        "هذه علامات مقترحة لمنتج عربي جمهوره يقرأ العربية. افتح صور كل مفهوم بالترتيب المذكور (الأكبر ثم الأصغر)، واكتب أول",
        "ما تراه العين في ثانيتين، لا ما تظن أن المصمم قصده. لا تقيّم الجودة ولا تقترح تعديلًا.", "",
        f"اكتب `{target}` بالضبط، بمدخل لكل معرّف من المعرّفات أدناه باسمه كما هو:", "", "```yaml", f"digest: {digest}", "readings:",
        f"  {ids[0] if ids else 'c1'}:",  # أول معرّف فعلي: القالب كان يثبّت c1 فيُكتب به والمعرّفات غيره (i0، w1) ويُهدر الاستدعاء
        '    seen: "ما تراه في جملة واحدة"',
        '    reads_as: "أقرب شيء معروف يُقرأ به الشكل، باسمه (ö، @، مؤشّر تحميل، مفتاح)؛ فارغ إن لم يُقرأ شيئًا"',
        f"    kind: {kinds}", "    strength: 0-3", "```", "",
        "kind: " + "؛ ".join(f"`{k}` = {v}" for k, v in KIND_AR.items()) + ".",
        "أمثلة: `foreign_letter` لاتيني أو يوناني أو هندي (a، ö، σ)؛ `common_symbol` مثل @ و# و☉ وعلامة الصح؛ `ui_icon` مثل مؤشّر",
        "التحميل وزر الطاقة ودبوس الموقع ومشبك الورق.",
        "strength: 0 لا قراءة؛ 1 شبه بعيد يحتاج تأملًا؛ 2 قراءة واضحة تزاحم غيرها؛ 3 أول ما يُرى ولا يُرى غيره.",
        "إن قرأتَ قراءتين فاكتب الأقوى في reads_as وkind واذكر الأخرى في seen.", "",
    ]
    if problems:
        lines += ["## مشاكل في ملف القراءة السابق لهذا المحتوى", *[f"- {p}" for p in problems], ""]
    for cid in ids:
        lines += [f"## {cid}", "الصور: " + ", ".join(str(p) for p in shots(cid)), ""]
    ws.write_request(name, "\n".join(lines))
