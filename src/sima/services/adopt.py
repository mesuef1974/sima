"""مدخل الاعتماد الخارجي: علامة واتجاه اعتمدهما المالك خارج خط الرسم (`identity.adopt` في الموجز).

البيان ملف YAML متتبَّع بجانب أصوله (الكلمة والرمز الصغير والنمط). الخدمة تتحقق منه تحققًا حتميًا وتكتب في الإصدار
ما كان الرسّام والحَكَم سيكتبانه: مفهومًا واحدًا معتمدًا بكلمات المالك، واتجاهًا واحدًا في `work/identity/`. لا يتغيّر في
الأصول إلا اللون (إلى الأسود) وتغليف الكلمة بمجموعة `id="wordmark"`؛ الهندسة تبقى كما اعتُمدت. وبوابتا الاتجاه والدليل
تبقيان للمالك في المنصة: الاتجاه يُعرض عليه مكتملًا (تدرجاته ووضعه الداكن وفحوصه) قبل أي حزمة.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from .. import config
from ..domain import Brief, Family, Medium, Verdict
from ..domain.identity import Gate
from . import svgtools
from .identity_protocol import digest as files_digest
from .identity_protocol import directions_path, idir, keep_adopted_direction, strategy_path, three_over_adopted
from .identity_protocol import ledger as identity_ledger
from .ledger import Ledger
from .workspace import Workspace, workspace_of

MARKER = "adopted"
CONCEPT_ID = "a1"
DIRECTION_ID = "d1"
MOTIF_FILE = f"motifs/{DIRECTION_ID}.svg"
_BW = {"#000000", "#FFFFFF"}
MIN_STROKE_FLOOR = 0.75  # أدنى حدّ سماكة يعلنه المالك (بكسل عند الحجم المعلن)؛ فوقه دون 1.5 الافتراضي (`config.MIN_STROKE_AT_16`)
MAX_MIN_MARK_PX = 320  # أعلى حدّ أدنى يُعلن للعلامة؛ فوق 96 تُفحص الكلمة عنده أيضًا (قرار المالك 2026-11-13 على «أوراق»، ورُفع من 192 لحدّ «مسك» 280 في 2026-11-19)


class AdoptError(ValueError):
    """بيان اعتماد ناقص أو لا يطابق ما ثُبّت فيه؛ يوقف التشغيل برسالة عربية ولا يُرسل شيء إلى النموذج.

    `content` ما يصحّحه صاحب الأصول في ملفاته («مفتاح: سبب»: SVG لا يُقرأ أو يردّه الفحص الثابت، مفهوم بلا اسم، اتجاه ليس
    بندًا)، و`other` ما سواه (بصمة لا تطابق، ملف غائب، حدّ خارج المدى): مسار المصمّم الخارجي يعيد الأول إليه ولا يعيد الثاني."""

    def __init__(self, message: str, *, content: list[str] | None = None, other: list[str] | None = None) -> None:
        super().__init__(message)
        self.content, self.other = list(content or []), list(other or [])


class PackagedError(AdoptError):
    """تغيّر البيان بعد بناء الحزمة بلا إذن بإعادة فتحها: قاعدة الخط لا خلل في الأصول، فلا تعود إلى من رسمها."""


@dataclass(frozen=True)
class Adoption:
    source: str  # مسار البيان كما في الموجز
    name: str
    sentence: str
    construction: str
    wordmark: str  # أسود على شفاف، الكلمة داخل id="wordmark"
    mark: str  # الرمز الصغير، أسود على شفاف
    motif: str
    direction: dict  # بصيغة بند directions.yaml
    min_mark_px: int
    owner_date: str
    owner_words: str
    strategy_from: str | None
    name_check_from: str | None
    digest: str
    shown: str = ""  # الاسم كما يُعرض في الوثائق إن اختلف عن `name` (مسار المصمّم: عنوان السكتش المختار ورقمه، ق2)؛ خارج البصمة
    min_stroke_px: float | None = None  # حدّ سماكة أدنى يعلنه المالك يغلب 1.5 (قراره 2026-11-15)؛ None = الحد الافتراضي
    min_wordmark_px: int | None = None  # أصغر عرض للشعار الكامل يعلنه المالك حين يكون الرمز أيقونة منفصلة (قراره 2026-11-20)
    min_wordmark_stroke_px: float | None = None  # سماكة الشعار الكامل عند حدّه المعلن؛ None = سماكة الرمز
    wordmark_color: str = "ink"  # "brand": الشعار الكامل كله بلون العلامة لا الكلمة بالحبر (قرار المالك 2026-11-20 لـ«مسك» v10)


def manifest_path(brief: Brief) -> Path | None:
    rel = brief.identity.adopt
    if not rel:
        return None
    if not brief.source_path:
        raise AdoptError("identity.adopt يحتاج موجزًا مقروءًا من ملف (المسار نسبي إلى مجلده)")
    return Path(brief.source_path).resolve().parent / rel


def load(brief: Brief) -> Adoption | None:
    path = manifest_path(brief)
    return None if path is None else load_manifest(path, str(brief.identity.adopt), fonts=brief.identity.fonts)


def load_manifest(path: Path, source: str, owner: tuple[str, str] | None = None, fonts: dict | None = None) -> Adoption:
    """يقرأ بيانًا ويتحقق منه. `owner` (التاريخ، الكلمات) يغلب ما في البيان حين يكون القرار مسجّلًا في الخط نفسه
    (اختيار السكتش في مسار المصمّم الخارجي)، فلا يكتب أحد كلمات المالك عنه. `fonts`: خطّا الهوية اللذان أعلنهما المالك في
    الموجز (`identity.fonts`، قراره 2026-11-15) يغلبان `type` في بند الاتجاه، قبل البصمة فتتغيّر ببدلهما وتُفتح البوابة."""
    if not path.is_file():
        raise AdoptError(f"بيان الاعتماد غير موجود: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise AdoptError(f"بيان الاعتماد YAML غير صالح: {e}") from e
    problems: list[str] = []
    content: list[str] = []  # ما في الأصول نفسها: يصحّحه من رسمها
    raw_pins = data.get("sha256")
    pins = {str(k): str(v).lower() for k, v in (raw_pins if isinstance(raw_pins, dict) else {}).items()}

    def asset(key: str) -> str:
        name = str(data.get(key) or "")
        f = path.parent / name
        if not name or ".." in name or not f.is_file():
            problems.append(f"{key}: ملف بجانب البيان وموجود")
            return ""
        raw = f.read_bytes().replace(b"\r\n", b"\n")  # البصمة لا تتأثر بتحويل git لنهايات الأسطر
        actual = hashlib.sha256(raw).hexdigest()
        if name not in pins:  # البصمة إلزامية: أصل بلا بصمة يتغيّر في مكانه ولا يُلحظ
            problems.append(f"{name}: بلا بصمة في sha256 بالبيان (بصمته الآن {actual})؛ ثبّتها عند الاعتماد")
        elif actual != pins[name]:
            problems.append(f"{name}: لا يطابق البصمة المثبّتة في البيان؛ المعتمد لا يُعدَّل")
        return raw.decode("utf-8")

    wordmark, mark, motif = asset("wordmark"), asset("mark"), asset("motif")
    concept, said = data.get("concept") or {}, data.get("owner") or {}
    name, sentence = str(concept.get("name") or "").strip(), str(concept.get("sentence") or "").strip()
    if not name or not sentence:
        content.append("concept: اسم وجملة الفكرة")
    words, date = str(said.get("words") or "").strip(), str(said.get("date") or "").strip()
    if owner is not None:
        date, words = owner
    if not words or not date:
        problems.append("owner: تاريخ القرار وكلمات المالك كما قالها")
    try:
        min_px = int(data.get("min_mark_px", 16))
    except (TypeError, ValueError):
        min_px = 0
    if not 16 <= min_px <= MAX_MIN_MARK_PX:
        problems.append(f"min_mark_px: عدد بين 16 و{MAX_MIN_MARK_PX}")
    min_stroke: float | None = None
    if data.get("min_stroke_px") is not None:
        try:
            min_stroke = round(float(data["min_stroke_px"]), 2)
        except (TypeError, ValueError):
            min_stroke = 0.0
        if not MIN_STROKE_FLOOR <= min_stroke < config.MIN_STROKE_AT_16:
            problems.append(f"min_stroke_px: عدد بين {MIN_STROKE_FLOOR:g} وأقل من {config.MIN_STROKE_AT_16:g}")
    min_wm: int | None = None
    if data.get("min_wordmark_px") is not None:
        try:
            min_wm = int(data["min_wordmark_px"])
        except (TypeError, ValueError):
            min_wm = 0
        if not 16 <= min_wm <= 4096:
            problems.append("min_wordmark_px: عدد بين 16 و4096")
    min_wm_stroke: float | None = None
    if data.get("min_wordmark_stroke_px") is not None:
        try:
            min_wm_stroke = round(float(data["min_wordmark_stroke_px"]), 2)
        except (TypeError, ValueError):
            min_wm_stroke = 0.0
        if min_wm is None:
            problems.append("min_wordmark_stroke_px: لا يُعلن بلا min_wordmark_px")
        elif not MIN_STROKE_FLOOR <= min_wm_stroke < config.MIN_STROKE_AT_16:
            problems.append(f"min_wordmark_stroke_px: عدد بين {MIN_STROKE_FLOOR:g} وأقل من {config.MIN_STROKE_AT_16:g}")
    tone = str(data.get("wordmark_color") or "ink")
    if tone not in ("ink", "brand"):
        problems.append("wordmark_color: ink (الكلمة بالحبر، الافتراضي) أو brand (الشعار كله بلون العلامة)")
    direction = data.get("direction")
    if not isinstance(direction, dict):
        content.append("direction: بند اتجاه واحد بصيغة directions.yaml")
        direction = {}
    direction = {**direction, "id": DIRECTION_ID,
                 "motif": {"file": MOTIF_FILE, "rule": str((direction.get("motif") or {}).get("rule") or "")}}
    if fonts:  # الأرقام تبقى كما في الاتجاه؛ المالك يعلن الخطين والوزنين وحدهما
        direction["type"] = {**(direction.get("type") or {}), "heading": dict(fonts["heading"]), "body": dict(fonts["body"])}
    if wordmark:  # بلا مجموعة id="wordmark" لا يلوّن التصدير الكلمة بالحبر فيبقى الشعار كله بلون العلامة
        wordmark = _bw(wordmark, "wordmark", content)
        wordmark = _as_wordmark(wordmark) if tone == "ink" else wordmark
    if mark:
        mark = _bw(mark, "mark", content)
    if problems or content:
        raise AdoptError("بيان الاعتماد: " + "؛ ".join(problems + content), content=content, other=problems)
    construction = str(concept.get("construction") or "").strip()
    # بصمة المحتوى الذي يدخل الإصدار، لا بصمة ملف البيان: تعليق أو بصمة تثبيت أو كلمات المالك لا تعيد فتح بوابة ولا تطلب إصدارًا
    content = {"name": name, "sentence": sentence, "construction": construction, "owner_date": date, "wordmark": wordmark, "mark": mark,
               "motif": motif, "direction": direction, "min_mark_px": min_px}
    if min_stroke is not None:  # بلا إعلان تبقى البصمات كما كانت
        content["min_stroke_px"] = min_stroke
    if min_wm is not None:
        content["min_wordmark_px"] = min_wm
    if min_wm_stroke is not None:
        content["min_wordmark_stroke_px"] = min_wm_stroke
    if tone != "ink":
        content["wordmark_color"] = tone
    digest = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return Adoption(
        source=source, name=name, sentence=sentence, construction=construction,
        wordmark=wordmark, mark=mark, motif=motif, direction=direction, min_mark_px=min_px, owner_date=date, owner_words=words,
        strategy_from=_opt(data.get("strategy_from")), name_check_from=_opt(data.get("name_check_from")), digest=digest,
        min_stroke_px=min_stroke, min_wordmark_px=min_wm, min_wordmark_stroke_px=min_wm_stroke, wordmark_color=tone,
    )


def _opt(v: object) -> str | None:
    return str(v) if v else None


def _bw(svg: str, key: str, problems: list[str]) -> str:
    """تغيير لون فقط: كل ما ليس none يصير أسود. الهندسة والسماكات كما هي."""
    try:
        out = svgtools.mono(svg)
    except Exception as e:  # noqa: BLE001 — ملف غير صالح يُبلَّغ مشكلةً في البيان
        problems.append(f"{key}: SVG غير صالح: {e}")
        return ""
    rep = svgtools.static_audit(out, allowed_colors=_BW, max_colors=2)
    problems.extend(f"{key}: {f}" for f in rep.findings)
    return out


def _as_wordmark(svg: str) -> str:
    """يغلّف محتوى الكلمة بمجموعة id="wordmark" ليلوّنها التصدير بلون الحبر في القفل."""
    if not svg:
        return svg
    root = svgtools.parse(svg)
    if any(el.get("id") == "wordmark" for el in root.iter()):
        return svg
    ns = root.tag.split("}", 1)[0] + "}" if root.tag.startswith("{") else ""
    g = root.makeelement(f"{ns}g", {"id": "wordmark"})
    for el in list(root):
        if svgtools._local(el.tag) in ("title", "desc", "defs"):
            continue
        root.remove(el)
        g.append(el)
    root.append(g)
    return svgtools.to_string(root)


def sync(ws: Workspace, a: Adoption, *, reopen: bool = False) -> None:
    """يكتب في الإصدار ما يحتاجه الخط من البيان. متساوي الأثر ببصمة البيان؛ تغيّره قبل الحزمة يعيد الكتابة فتُفتح بوابة
    الاتجاه من جديد (القرار مربوط بالمحتوى)، وبعدها يلزم إصدار جديد. `reopen` استثناء واحد يقرّره المستدعي: اعتمادٌ ردّه المالك
    بسبب مسجَّل في إصدار لم يُغلق (مسار المصمّم الخارجي) يحلّ محلّه تسليم جديد وتُبنى الحزمة عليه.

    ونسخ العمل للعلامة (`work/concepts.yaml` و`work/concepts/a1*.svg`) داخل نافذة كتابة نموذج الخط: تُقارَن بما يكتبه البيان عند
    كل تشغيل ولو طابقت البصمة، ويُعاد ما اختلف منها، فلا يُحزَم إلا المعتمد (ب11)."""
    marker = ws.read_marker(MARKER)
    files = _outputs(ws, a)
    if marker.get("digest") == a.digest:
        _restore(ws, files)
        return
    if marker and marker.get("min_mark_px") == a.min_mark_px and all(
            f.is_file() and f.read_text(encoding="utf-8") == text for f, text in files.items()):
        return  # علامة ببصمة الملف القديمة (قبل بصمة المحتوى) وما في الإصدار هو ما يكتبه البيان الآن: لم يتغيّر شيء
    if ws.done("package"):
        if not reopen:
            raise PackagedError("تغيّر بيان الاعتماد بعد بناء الحزمة؛ افتح إصدارًا جديدًا بـ --new-version.")
        ws.marker("package").unlink()  # ردّ المالك المتجه المبني قبل اعتماد الدليل: تُبنى الحزمة من جديد على التسليم الجديد
    # ثلاثة اتجاهات فوق العلامة (`identity.directions: three`): الاتجاهان الآخران كتبهما نموذج الخط واختار المالك منها؛ تسليم
    # جديد يبدّل اتجاهه `d1` وحده ولا يمحوهما (ب8). قرار المالك مربوط ببصمة الثلاثة: يبقى إن لم يتغيّر `d1`
    merge = three_over_adopted(ws) and _has_other_directions(ws)
    for f, text in files.items():
        if merge and f == directions_path(ws):
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    if merge:
        keep_adopted_direction(ws, a.direction, a.motif)
    if not marker:
        _carry_strategy(ws, a)
        _carry_name_check(ws, a)
        ledger = Ledger(ws.ledger_path)
        if ledger.approved() is None:
            ledger.record(CONCEPT_ID, Verdict.APPROVED, Medium.WORDMARK, f"اعتماد المالك خارج الخط ({a.owner_date}): {a.owner_words}")
    ws.mark_done(MARKER, {"digest": a.digest, "from": a.source, "min_mark_px": a.min_mark_px})


def _restore(ws: Workspace, files: dict[Path, str]) -> None:
    """نسخ العمل للعلامة المعتمدة كما يكتبها البيان؛ متساوي الأثر: لا يكتب إن لم يختلف شيء. الاتجاه ونمطه ليسا منها: تعديلهما
    يمرّ ببوابة الاتجاه ببصمتها."""
    for f in (ws.work / "concepts.yaml", ws.concepts_dir / f"{CONCEPT_ID}.svg", ws.concepts_dir / f"{CONCEPT_ID}.small.svg"):
        if not f.is_file() or f.read_text(encoding="utf-8") != files[f]:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(files[f], encoding="utf-8")


def _has_other_directions(ws: Workspace) -> bool:
    try:
        data = yaml.safe_load(directions_path(ws).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    items = data.get("directions") if isinstance(data, dict) else None
    return isinstance(items, list) and any(isinstance(x, dict) and x.get("id") != DIRECTION_ID for x in items)


def _outputs(ws: Workspace, a: Adoption) -> dict[Path, str]:
    """ما يكتبه البيان في الإصدار: المفهوم الواحد بكلمته ورمزه، والاتجاه الواحد بنمطه."""
    concepts = yaml.safe_dump({"concepts": [{
        "id": CONCEPT_ID, "name": a.shown or a.name, "family": Family.TYPOGRAPHIC.value, "medium": Medium.WORDMARK.value, "sentence": a.sentence,
        "construction": a.construction, "reference": f"اعتماد المالك خارج الخط ({a.owner_date})",
    }]}, allow_unicode=True, sort_keys=False)
    return {
        ws.work / "concepts.yaml": concepts,
        ws.concepts_dir / f"{CONCEPT_ID}.svg": a.wordmark,
        ws.concepts_dir / f"{CONCEPT_ID}.small.svg": a.mark,
        idir(ws) / MOTIF_FILE: a.motif,
        directions_path(ws): yaml.safe_dump({"directions": [a.direction]}, allow_unicode=True, sort_keys=False),
    }


def _carry_strategy(ws: Workspace, a: Adoption) -> None:
    """المنصة الاستراتيجية من إصدار سابق، ومعها اعتماد المالك إن كان على هذا المحتوى بعينه (بالبصمة)."""
    if not a.strategy_from or strategy_path(ws).is_file():
        return
    root = ws.root.parent / a.strategy_from
    if not (root / "run.json").is_file() or not strategy_path(workspace_of(root)).is_file():
        raise AdoptError(f"strategy_from: لا منصة استراتيجية في {root}")
    src = workspace_of(root)
    idir(ws).mkdir(parents=True, exist_ok=True)
    shutil.copy2(strategy_path(src), strategy_path(ws))
    dg = files_digest([strategy_path(ws)])
    dec = identity_ledger(src).latest(Gate.STRATEGY, dg)
    if dec is not None and dec.verdict == "approved":
        identity_ledger(ws).record(Gate.STRATEGY, dg, "approved", dec.option, f"منقول من {a.strategy_from} ({dec.at}): {dec.reason}".strip(" :"))


def _carry_name_check(ws: Workspace, a: Adoption) -> None:
    if not a.name_check_from or ws.name_check_path.is_file():
        return
    src = ws.root.parent / a.name_check_from
    for name in (ws.name_check_path.name, "NAME-CHECK.md"):
        if (src / name).is_file():
            shutil.copy2(src / name, ws.root / name)
