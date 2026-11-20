"""مسار المصمّم الخارجي (قرار المالك 2026-11-13، `identity.designer: external` في الموجز).

الرسم خارج الخط والفحص داخله: مصمّم خارجي (ChatGPT في حساب المالك، تُشغّله الجلسة يدويًّا ولا تستدعيه سِمة) يرسم صفحة
سكتشات مرقّمة، والمالك يختار منها واحدًا في المنصة، ثم يبني المصمّم المختار متجهًا كما هو ويسلّم ملفاته واتجاه هويته.
سِمة تكتب نص كل طلب من الموجز، وتستلم الناتج في `designer/` من الإصدار، وتحوّله إلى بيان اعتماد خارجي ببصماته
(`services/adopt.py`) فتفحصه وتبني الهوية. وبعد اختيار السكتش لا يعود الخط إلى المالك إلا بالدليل (`RULE`)،
وتحقق الاسم يبقى له لأنه تحقق يدوي لا قرار تصميم.

لا يُرسل إلى الخارج إلا نص الطلب، ولا يُكتب في هذه الخدمة أي اتصال شبكي.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .. import config
from ..domain import Brief
from . import adopt
from .workspace import Workspace

EXTERNAL = "external"
MARKER = "designer_sketches"
REQ_SKETCHES = "REQUEST-designer-sketches.md"
REQ_VECTOR = "REQUEST-designer-vector.md"
REQ_FIX = "REQUEST-designer-fix.md"
FIX_MARKER = "designer_fix"
FIX_ROUNDS = 3  # جولات التصحيح الآلي قبل أن يُعرض الحال على المالك
FIX_GATE = "designer_fix"  # اسم وقوف الخط عند المالك حين تُستنفد الجولات؛ ببصمة التسليم المردود
REOPEN_MARKER = "designer_reopen"  # تسليم قبِله المالك بحدّ معلن بعد بناء الحزمة: يعيد فتحها مرة واحدة ببصمة بيانه
BY_OWNER, BY_DELIVERY = "owner", "delivery"  # من أعلن الحد الأدنى في البيان
SHOWN_TITLE_MAX = 40  # أطول عنوان فكرة يُعرض اسمًا للعلامة؛ فكرة بلا عنوان قصير قبل النقطتين تُعرض برقم سكتشها
REJECTED_DIR = "rejected"  # صفحات سكتشات رفضها المالك، كل واحدة في مجلد ببصمتها
DEVELOPED_DIR = "developed"  # صفحات اختار المالك منها سكتشًا وطلب تطويره بصفحة حوله قبل بنائه
REBUILT_DIR = "rebuilt"  # تسليمات متجهة ردّها المالك بسبب، كل واحد في مجلد ببصمة بيانه
MIN_REASON = 3
FILE_OF = {"a1": "logo.svg", "a1-small": "icon.svg", "direction": "direction.yaml",  # مفاتيح الفحص، ثم مفاتيح بيان الاعتماد
           "wordmark": "logo.svg", "mark": "icon.svg", "motif": "motif.svg", "concept": "concept.yaml"}
SENT = "## النص المرسل (هذا وحده)"
RULE = "مسار المصمّم الخارجي: يُعرض ضمن الدليل، وهو قرار المالك الوحيد بعد السكتش (قراره 2026-11-13)"
HARAKAT = re.compile(f"[{chr(0x64B)}-{chr(0x652)}]")  # التشكيل (فتحتان إلى سكون) لا يفرّق بين اسمين
IMAGE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}\.(jpg|png)")
ASSETS = {"wordmark": "logo.svg", "mark": "icon.svg", "motif": "motif.svg"}
CRITERIA = ("فكرة واحدة تُشرح في جملة؛ بناء هندسي بنِسب وسماكات متسقة؛ فراغ سلبي يحمل معنى ثانيًا إن أمكن؛ صورة ظلّية تُعرف من "
            "حدّها الخارجي؛ بساطة تُرسم من الذاكرة؛ صمود عند 16 بكسل؛ بلا ملمس ولا ظل ولا تدرّج ولا mockup.")
CLICHES = ("الشرارة والنجمة الرباعية ورموز الذكاء الاصطناعي", "بصمة الإصبع", "علامة الصح", "المربع المستدير بأيقونة داخله",
           "أيقونات الواجهات الشائعة", "أي شبه بشعار معروف")


class DesignerError(ValueError):
    """استلام ناقص أو اختيار لا يطابق المعروض؛ رسالة عربية ولا يتقدّم الخط."""


class OtherSketch(adopt.AdoptError):
    """البيان الحاضر مبني لسكتش غير الذي اختاره المالك: لم يُستلم متجه المختار بعد، وليس في التسليم ما يُصحَّح."""


@dataclass(frozen=True)
class Sheet:
    image: str
    source: str
    sketches: tuple[tuple[int, str], ...]  # (الرقم كما في الصورة، الفكرة في جملة)
    picks: tuple[int, ...]  # أقوى ثلاثة عند المصمّم: رأيه للاطلاع، والاختيار للمالك
    digest: str


def enabled(brief: Brief) -> bool:
    return brief.identity.designer == EXTERNAL


def frozen_enabled(version_root: Path) -> bool:
    """من الموجز المجمَّد في الإصدار: ما شُغّل به فعلًا."""
    try:
        data = json.loads((version_root / "brief.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data.get("identity"), dict) and data["identity"].get("designer") == EXTERNAL


def ddir(ws: Workspace) -> Path:
    return ws.root / "designer"


def sheet_path(ws: Workspace) -> Path:
    return ddir(ws) / "sketches.yaml"


def manifest_path(ws: Workspace) -> Path:
    return ddir(ws) / "adopt.yaml"


def decisions_path(ws: Workspace) -> Path:
    return ws.root / "designer_decisions.jsonl"


def read_sheet(ws: Workspace) -> tuple[Sheet | None, list[str]]:
    """صفحة السكتشات كما استُلمت: صورة واحدة وقائمة مرقّمة بفكرة كل سكتش. الناقص يُذكر ولا يُعرض على المالك."""
    p = sheet_path(ws)
    if not p.is_file():
        return None, []
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        return None, [f"sketches.yaml غير صالح: {e}"]
    if not isinstance(data, dict):
        return None, ["sketches.yaml: قاموس فيه image وsketches"]
    problems: list[str] = []
    image = str(data.get("image") or "")
    img = ddir(ws) / image
    if not IMAGE.fullmatch(image) or not img.is_file():
        problems.append("image: صورة jpg أو png باسم بسيط بجانب sketches.yaml")
    rows = data.get("sketches")
    sketches: list[tuple[int, str]] = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and isinstance(r.get("id"), int) and str(r.get("idea") or "").strip():
            sketches.append((r["id"], str(r["idea"]).strip()))
    ids = [i for i, _ in sketches]
    if not isinstance(rows, list) or len(sketches) != len(rows) or ids != list(range(1, len(ids) + 1)):
        problems.append("sketches: قائمة {id, idea} مرقّمة من 1 بلا فجوات، بفكرة لكل سكتش")
    elif not config.DESIGNER_SKETCHES_MIN <= len(sketches) <= config.DESIGNER_SKETCHES_MAX:
        problems.append(f"sketches: من {config.DESIGNER_SKETCHES_MIN} إلى {config.DESIGNER_SKETCHES_MAX} سكتشًا")
    raw = data.get("picks")
    picks = tuple(x for x in (raw if isinstance(raw, list) else []) if isinstance(x, int) and x in ids)
    if problems:
        return None, problems
    h = hashlib.sha256(img.read_bytes())
    h.update(json.dumps(sketches, ensure_ascii=False).encode("utf-8"))
    return Sheet(image, str(data.get("source") or ""), tuple(sketches), picks, h.hexdigest()[:16]), []


def choices(ws: Workspace) -> list[dict]:
    p = decisions_path(ws)
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _last(ws: Workspace, sheet: Sheet) -> dict | None:
    return next((c for c in reversed(choices(ws)) if c.get("digest") == sheet.digest), None)


def current(ws: Workspace, sheet: Sheet) -> dict | None:
    """آخر اختيار على هذه الصفحة بعينها؛ صفحة جديدة تفتح البوابة من جديد. الرفض ليس اختيارًا."""
    row = _last(ws, sheet)
    return row if row is not None and "sketch" in row and not row.get("develop") else None


def development(ws: Workspace, sheet: Sheet) -> dict | None:
    """طلب المالك تطوير سكتش من هذه الصفحة بعينها إن كان آخر قراره عليها: الخط ينتظر صفحة معالجات حوله من المصمّم."""
    row = _last(ws, sheet)
    return row if row is not None and row.get("develop") else None


def pending_development(ws: Workspace) -> dict | None:
    """آخر قرار للمالك إن كان طلب تطوير: يبقى معلّقًا حتى تصل صفحة صالحة غير التي طُلب منها (ولو وصلت ناقصة أولًا)."""
    rows = choices(ws)
    return rows[-1] if rows and rows[-1].get("develop") else None


def rejection(ws: Workspace, sheet: Sheet) -> dict | None:
    """رفض المالك لهذه الصفحة بعينها إن كان آخر قراره عليها: الخط ينتظر صفحة جديدة من المصمّم."""
    row = _last(ws, sheet)
    return row if row is not None and row.get("rejected") else None


def rejections(ws: Workspace) -> list[dict]:
    """كل ما رفضه المالك من صفحات هذا الإصدار بترتيبه؛ أسبابه تدخل طلب الصفحة التالية بنصّها."""
    return [c for c in choices(ws) if c.get("rejected")]


def prior_rejections(ws: Workspace) -> list[dict]:
    """ما رُفض في الإصدار السابق مباشرةً إن تُرك مفتوحًا عند صفحة مرفوضة: حين يُعدَّل الموجز استجابةً لسبب الرفض يتغيّر المفتاح
    ويُفتح إصدار جديد، وسبب المالك لا يضيع معه بل يدخل طلب الصفحة التالية."""
    prev = ws.root.parent / f"v{ws.version - 1}"
    run, p = prev / "run.json", prev / "designer_decisions.jsonl"
    if not (run.is_file() and p.is_file()) or json.loads(run.read_text(encoding="utf-8")).get("closed"):
        return []
    rows = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [r for r in rows if r.get("rejected")] if rows and rows[-1].get("rejected") else []


def reject(ws: Workspace, sheet: Sheet, reason: str, shown_digest: str) -> dict:
    """رفض الصفحة كلها بسبب (قرار المالك 2026-11-13): تعود إلى المصمّم بسببه بنصّه، والمرفوضة تُحفظ في `designer/rejected/`
    ببصمتها فلا تضيع حين تحلّ الصفحة الجديدة محلّها."""
    if shown_digest != sheet.digest:
        raise DesignerError("تغيّرت صفحة السكتشات منذ عرضها؛ حدّث الصفحة ثم قرّر من جديد.")
    reason = reason.strip()
    if len(reason) < MIN_REASON:
        raise DesignerError("اكتب سبب الرفض أولًا؛ يُنقل إلى المصمّم بنصّه.")
    _keep(ws, sheet, REJECTED_DIR)
    return _append(ws, {"rejected": True, "reason": reason, "digest": sheet.digest})


def _keep(ws: Workspace, sheet: Sheet, folder: str) -> None:
    keep = ddir(ws) / folder / sheet.digest
    keep.mkdir(parents=True, exist_ok=True)
    for f in (sheet_path(ws), ddir(ws) / sheet.image):
        shutil.copy2(f, keep / f.name)


def _append(ws: Workspace, row: dict) -> dict:
    row = {**row, "at": datetime.now(UTC).isoformat(timespec="seconds")}
    with decisions_path(ws).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _shown(sheet: Sheet, sketch: int, shown_digest: str) -> None:
    if shown_digest != sheet.digest:
        raise DesignerError("تغيّرت صفحة السكتشات منذ عرضها؛ حدّث الصفحة ثم اختر من جديد.")
    if sketch not in {i for i, _ in sheet.sketches}:
        raise DesignerError(f"اختر رقمًا من 1 إلى {len(sheet.sketches)} كما في الصفحة.")


def develop(ws: Workspace, sheet: Sheet, sketch: int, note: str, shown_digest: str) -> dict:
    """«طوّر هذا السكتش» (طلب المالك 2026-11-13): لا يُبنى متجهًا بعد؛ يعود إلى المصمّم ليرسم صفحة كلها معالجات لفكرته،
    بملاحظة المالك بنصّها. الصفحة الأصل تُحفظ في `designer/developed/` ببصمتها، والفكرة تُسجَّل مع القرار."""
    _shown(sheet, sketch, shown_digest)
    _keep(ws, sheet, DEVELOPED_DIR)
    return _append(ws, {"develop": True, "sketch": sketch, "idea": dict(sheet.sketches)[sketch], "note": note.strip(), "digest": sheet.digest})


def record(ws: Workspace, sheet: Sheet, sketch: int, note: str, shown_digest: str) -> dict:
    _shown(sheet, sketch, shown_digest)
    return _append(ws, {"sketch": sketch, "note": note.strip(), "digest": sheet.digest})


def manifest_digest(ws: Workspace) -> str:
    """بصمة بيان الاعتماد الحاضر كما هو على القرص، أو فارغ إن لم يُستلم تسليم بعد."""
    p = manifest_path(ws)
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.is_file() else ""


def _manifest(ws: Workspace) -> dict:
    try:
        data = yaml.safe_load(manifest_path(ws).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def manifest_min(ws: Workspace) -> int:
    """الحد الأدنى في البيان الحاضر كما هو، أو 16 إن لم يُقرأ."""
    try:
        return int(_manifest(ws).get("min_mark_px", 16))
    except (TypeError, ValueError):
        return 16


def declared_min(ws: Workspace, sketch: int) -> int | None:
    """الحد الأدنى الذي أعلنه المالك للعلامة المبنية لهذا السكتش، من البيان الحاضر؛ None إن لم يعلن. قرار المالك يُحمل إلى
    كل تسليم لاحق للسكتش نفسه ما لم يغيّره صراحة (ب6: كان أي استلام بلا حدّ يعيده إلى 16). وبيان أقدم من حقل `min_mark_px_by`:
    طلب المتجه لا يسأل المصمّم عن حدّ، فما ليس 16 فيه أعلنه المالك."""
    data = _manifest(ws)
    if data.get("sketch") != sketch:
        return None
    by, px = data.get("min_mark_px_by"), manifest_min(ws)
    return px if by == BY_OWNER or (by is None and px != 16) else None


def declared_stroke(ws: Workspace, sketch: int) -> float | None:
    """حدّ السماكة الذي أعلنه المالك للعلامة المبنية لهذا السكتش من البيان الحاضر؛ None إن لم يعلن. يُحمل كالحدّ الأدنى للعرض
    إلى كل تسليم لاحق للسكتش نفسه. المصمّم لا يعلنه: يُقرأ فقط ما كُتب بيد المالك (`min_stroke_px_by: owner`)."""
    data = _manifest(ws)
    if data.get("sketch") != sketch or data.get("min_stroke_px_by") != BY_OWNER:
        return None
    try:
        return float(data["min_stroke_px"])
    except (KeyError, TypeError, ValueError):
        return None


def build(ws: Workspace) -> str:
    """البناء الجاري: آخر قرار للمالك على الصفحة الحاضرة (اختيار سكتش، أو ردّ متجهه). جولات التصحيح تُعدّ له وحده."""
    sheet, _ = read_sheet(ws)
    if sheet is None or current(ws, sheet) is None:
        return ""
    rows = choices(ws)  # موضع القرار في سجله لا وقته: اختيار وردّ في الثانية نفسها بناءان
    at = max(i for i, c in enumerate(rows) if c.get("digest") == sheet.digest)
    return f"{sheet.digest}:{rows[at].get('sketch')}:{at}"


def reopened_by_owner(ws: Workspace) -> bool:
    """هل البيان الحاضر تسليم قبِله المالك بحدّ معلن بعد بناء الحزمة؟ عندها يُعاد بناؤها عليه، لهذا البيان وحده."""
    return bool(manifest_digest(ws)) and ws.read_marker(REOPEN_MARKER).get("manifest") == manifest_digest(ws)


def rebuild(ws: Workspace, sheet: Sheet, reason: str) -> dict:
    """ردّ المالك المتجه المبني بسبب (قراره 2026-11-13 على دليل «أوراق»: «ليس هذا الشعار الذي اتفقنا عليه»): السكتش المختار
    نفسه يعود إلى المصمّم بسبب المالك بنصّه ليبنيه من جديد. الاختيار باقٍ كما هو، والتسليم المردود يُحفظ في `designer/rebuilt/`
    ببصمة بيانه. القرار مربوط بالبيان المردود وباعتماده في الإصدار: لا يُستبدل به إلا تسليم واحد جديد."""
    choice, built = current(ws, sheet), manifest_digest(ws)
    if choice is None or not built:
        raise DesignerError("لا متجه مستلَم لسكتش مختار؛ ردّ المتجه يتبع استلامه.")
    if choice.get("rebuild") and choice.get("manifest") == built:
        raise DesignerError("هذا المتجه مردود من قبل، والخط ينتظر بناءه من جديد.")
    reason = reason.strip()
    if len(reason) < MIN_REASON:
        raise DesignerError("اكتب سبب ردّ المتجه أولًا؛ يُنقل إلى المصمّم بنصّه.")
    keep = ddir(ws) / REBUILT_DIR / built
    keep.mkdir(parents=True, exist_ok=True)
    for f in (manifest_path(ws), *(ddir(ws) / name for name in ASSETS.values())):
        if f.is_file():
            shutil.copy2(f, keep / f.name)
    return _append(ws, {"sketch": choice["sketch"], "note": str(choice.get("note") or ""), "rebuild": True, "reason": reason,
                        "manifest": built, "adopted": str(ws.read_marker(adopt.MARKER).get("digest", "")), "digest": sheet.digest})


def rebuilds(ws: Workspace, sheet: Sheet, sketch: int) -> list[dict]:
    """كل ما ردّه المالك من تسليمات هذا السكتش بترتيبه؛ أسبابه تدخل طلب إعادة البناء بنصّها."""
    return [c for c in choices(ws) if c.get("rebuild") and c.get("digest") == sheet.digest and c.get("sketch") == sketch]


def pending_rebuild(ws: Workspace, sheet: Sheet) -> dict | None:
    """ردّ المالك للمتجه إن كان آخر قراره على هذه الصفحة والتسليم المردود ما زال هو الحاضر: الخط ينتظر بناءً جديدًا من المصمّم."""
    row = current(ws, sheet)
    return row if row is not None and row.get("rebuild") and row.get("manifest") == manifest_digest(ws) else None


def replaces_rejected(ws: Workspace, choice: dict) -> bool:
    """هل الاعتماد القائم في الإصدار هو الذي ردّه المالك؟ عندها يحلّ التسليم الجديد محلّه ولو بُنيت الحزمة، مرة واحدة."""
    return bool(choice.get("rebuild")) and str(ws.read_marker(adopt.MARKER).get("digest", "")) == choice.get("adopted")


def owner_words(choice: dict, sheet: Sheet) -> tuple[str, str]:
    idea = dict(sheet.sketches).get(choice["sketch"], "")
    words = f"اختار السكتش {choice['sketch']} في منصة سِمة: {idea}"
    return str(choice["at"])[:10], words + (f" — ملاحظته: {choice['note']}" if choice.get("note") else "")


def adoption(ws: Workspace, sheet: Sheet, choice: dict, fonts: dict | None = None) -> adopt.Adoption | None:
    """بيان الاعتماد المكتوب من تسليم المصمّم للسكتش المختار، أو None إن لم يُستلم بعد. بيان لسكتش آخر مشكلة تُذكر."""
    p = manifest_path(ws)
    if not p.is_file():
        return None
    try:
        built_for = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("sketch")
    except yaml.YAMLError as e:
        raise adopt.AdoptError(f"بيان الاعتماد YAML غير صالح: {e}") from e
    if built_for != choice["sketch"]:
        raise OtherSketch(f"المتجه المستلم مبني للسكتش {built_for} والمالك اختار {choice['sketch']}")
    return replace(adopt.load_manifest(p, "designer/adopt.yaml", owner=owner_words(choice, sheet), fonts=fonts),
                   shown=shown_name(sheet, choice["sketch"]))


def shown_name(sheet: Sheet, sketch: int) -> str:
    """اسم العلامة كما يُعرض في الوثائق (قرار المالك ق2، 2026-11-14): عنوان فكرة السكتش الذي اختاره مع رقمه. الاسم الذي يضعه
    المصمّم في concept.yaml لم يُسأل عنه المالك (سمّى متجه السكتش 11 «التراكب الأفقي» باسم اتجاهٍ لم يختره)، فيبقى حقل تتبّع في
    البيان وبصمته ولا يُعرض."""
    head, colon, _ = dict(sheet.sketches).get(sketch, "").partition(":")
    title = head.strip() if colon and 0 < len(head.strip()) <= SHOWN_TITLE_MAX else ""
    return f"{title} (السكتش {sketch})" if title else f"السكتش {sketch}"


def write_manifest(ws: Workspace, sketch: int, source_dir: Path, min_mark_px: int | None = None,
                   min_stroke_px: float | None = None) -> Path:
    """يحوّل تسليم المصمّم (logo.svg وicon.svg وmotif.svg وdirection.yaml وconcept.yaml في مجلد) إلى بيان اعتماد ببصماته
    داخل الإصدار. لا يعدّل الملفات؛ التحقق كله في `adopt.load_manifest` عند التشغيل. `min_mark_px` حدّ أدنى يعلنه المالك
    عند الاستلام فيغلب ما في concept.yaml: به يقبل علامة رفيعة كما هي فوق حجم معلوم بدل تغليظها (قراره 2026-11-13)،
    ويُحمل إلى كل تسليم لاحق للسكتش نفسه ما لم يغيّره (`declared_min`).

    الباب واحد للطرفية والصندوق (ب9): إصدار اعتُمد دليله لا يدخله تسليم؛ وبعد بناء الحزمة لا يدخل إلا تسليم يحلّ محلّ متجه
    ردّه المالك، أو تسليم يقبله المالك بحدّ يعلنه الآن فتُبنى الحزمة والدليل عليه (مرة لذلك البيان)."""
    if min_mark_px is not None and not 16 <= min_mark_px <= adopt.MAX_MIN_MARK_PX:
        raise DesignerError(f"الحد الأدنى المعلن للعلامة عدد بين 16 و{adopt.MAX_MIN_MARK_PX} بكسل.")  # خطأ المالك لا يعود إلى المصمّم
    if min_stroke_px is not None and not adopt.MIN_STROKE_FLOOR <= min_stroke_px < config.MIN_STROKE_AT_16:
        raise DesignerError(f"حدّ السماكة المعلن عدد بين {adopt.MIN_STROKE_FLOOR:g} وأقل من {config.MIN_STROKE_AT_16:g} بكسل.")
    if ws.done("identity"):
        raise DesignerError("هذا الإصدار اعتُمد دليله واكتمل؛ تسليم جديد يلزمه إصدار جديد.")
    sheet, _ = read_sheet(ws)
    choice = current(ws, sheet) if sheet is not None else None
    packaged = ws.done("package") and not (choice is not None and replaces_rejected(ws, choice))
    if packaged and min_mark_px is None and min_stroke_px is None:
        raise DesignerError("هذا التسليم بعد بناء الحزمة ولم يُردّ المتجه القائم، فلا يدخل الإصدار: ردّ الشعار بسبب من بطاقة الدليل "
                            "ليحلّ محلّه تسليم جديد، أو أعلن حدّه الأدنى بـ--min-mark-px أو حدّ سماكته بـ--min-stroke-px "
                            "ليُعاد بناء الحزمة والدليل عليه.")
    missing =[n for n in (*ASSETS.values(), "direction.yaml", "concept.yaml") if not (source_dir / n).is_file()]
    if missing:
        raise DesignerError("تسليم المصمّم ناقص: " + "، ".join(missing))
    try:
        direction = yaml.safe_load((source_dir / "direction.yaml").read_text(encoding="utf-8"))
        concept = yaml.safe_load((source_dir / "concept.yaml").read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise DesignerError(f"direction.yaml أو concept.yaml غير صالح: {e}") from e
    if not isinstance(direction, dict) or not isinstance(concept, dict):
        raise DesignerError("direction.yaml وconcept.yaml: قاموس في كل منهما")
    declared = min_mark_px if min_mark_px is not None else declared_min(ws, sketch)
    out = ddir(ws)
    out.mkdir(parents=True, exist_ok=True)
    pins = {}
    for name in ASSETS.values():
        raw = (source_dir / name).read_bytes().replace(b"\r\n", b"\n")
        (out / name).write_bytes(raw)
        pins[name] = hashlib.sha256(raw).hexdigest()
    data = {"sketch": sketch, "concept": {k: str(concept.get(k) or "") for k in ("name", "sentence", "construction")},
            **ASSETS, "min_mark_px": int(declared if declared is not None else concept.get("min_mark_px", 16)),
            "min_mark_px_by": BY_OWNER if declared is not None else BY_DELIVERY, "sha256": pins, "direction": direction}
    stroke = min_stroke_px if min_stroke_px is not None else declared_stroke(ws, sketch)
    if stroke is not None:
        data["min_stroke_px"], data["min_stroke_px_by"] = round(stroke, 2), BY_OWNER
    manifest_path(ws).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    if packaged:
        ws.mark_done(REOPEN_MARKER, {"manifest": manifest_digest(ws)})
    return manifest_path(ws)


def mark_name(brief: Brief) -> str:
    """الاسم الذي يحمله الشعار: الاسم المختصر إن اختلف عن الاسم الكامل بغير التشكيل («أوراق» لا «مولّد أوراق الرياضيات»)،
    وإلا الاسم الكامل بتشكيله («وَتَد»)."""
    short = brief.wordmark_text
    return brief.name_ar if HARAKAT.sub("", short) == HARAKAT.sub("", brief.name_ar) else short


def _named(brief: Brief) -> str:
    name = mark_name(brief)
    return f"«{name}»" if name == brief.name_ar else f"«{name}» (اسمها الوصفي الكامل: {brief.name_ar})"


def _brief_lines(brief: Brief) -> list[str]:
    avoid = [*brief.taste.avoid, *brief.taste.dislikes, *CLICHES]
    return [
        f"العلامة: {brief.sector}.",
        *([f"المنتج بالتفصيل: {brief.product}"] if brief.product else []),
        f"جمهورها: {brief.audience}.",
        f"غايتها: {brief.purpose}.",
        f"كلماتها الثلاث: {'، '.join(brief.three_words)}. شخصيتها: {brief.archetype}.",
        f"إحساسها: {brief.taste.feeling}",
        f"تُستعمل في: {'؛ '.join(brief.contexts)}.",
        "تجنّب صراحةً: " + "؛ ".join(avoid) + ".",
    ]


def _rejected_lines(rejected: list[str]) -> list[str]:
    """ما رفضه صاحب العلامة بنصّه، بلا تأويل ولا اقتراح علاج: العلاج عمل المصمّم."""
    if not rejected:
        return []
    earlier = ["ورفض قبلها صفحات أخرى لهذه الأسباب: " + "؛ ".join(f"«{r}»" for r in rejected[:-1]) + "."] if rejected[:-1] else []
    return [
        f"صاحب العلامة رفض صفحة السكتشات السابقة كلها ولم يختر منها. سببه بنصّه: «{rejected[-1]}».", *earlier,
        "ارسم صفحة جديدة تعالج هذا السبب، بأفكار مختلفة: لا تُعد سكتشًا من المرفوض ولا تنويعًا عليه. المواصفات كما هي:", "",
    ]


def _develop_lines(develop: dict) -> list[str]:
    """طلب المالك تطوير سكتش اختاره، بنصّه وبلا تأويل: كيف تُطوَّر الفكرة عمل المصمّم."""
    return [
        f"صاحب العلامة اختار من صفحة السكتشات السابقة السكتش رقم {develop['sketch']}: «{develop['idea']}».",
        *([f"طلبه بنصّه: «{develop['note']}»."] if develop.get("note") else []),
        "لم يطلب بناءه متجهًا بعد: ارسم صفحة سكتشات جديدة كلها تطوير لهذه الفكرة نفسها بصقل احترافي. المواصفات كما هي:", "",
    ]


def sketch_prompt(brief: Brief, rejected: list[str] | None = None, develop: dict | None = None) -> str:
    n = config.DESIGNER_SKETCHES
    each = (("كل سكتش فكرة مختلفة", "لا تنويع على جاره.") if develop is None else
            ("كل سكتش معالجة مختلفة للفكرة", "المختارة نفسها (بناءً ونِسبًا وسماكة وفراغًا سلبيًّا)، لا فكرة أخرى ولا تكرار لجاره."))
    latin = f" (باللاتينية {brief.name_latin})" if brief.name_latin else ""
    return "\n".join([
        *(_develop_lines(develop) if develop else _rejected_lines(rejected or [])),
        f"أنت مصمّم هويات بصرية محترف. ارسم صفحة سكتشات واحدة، صورة أفقية 3:2، لشعار علامة اسمها {_named(brief)}{latin}.", "",
        *_brief_lines(brief), "",
        f"المطلوب: {n} سكتشًا في شبكة 4×4 بقلم رصاص على ورق منقّط، بخطوط البناء والدوائر والمحاور ظاهرة. {each[0]}",
        f"{each[1]} في ركن كل خانة رقمها من 1 إلى {n} واضحًا مقروءًا. شعار حديث يقوده رمز ذكي؛ كتابة الاسم ليست شرطًا،",
        "وإن كُتب فبحروف عربية سليمة الإملاء متصلة كما تُكتب.", "",
        f"معايير كل سكتش: {CRITERIA}", "",
        f"بعد الصورة اكتب قائمة مرقّمة من 1 إلى {n}: فكرة كل سكتش في جملة واحدة. ثم سطرًا بأقوى ثلاثة عندك ولماذا.",
        "لا تنتقل إلى الشعار النهائي: الاختيار لصاحب العلامة.",
    ])


def write_sketch_request(ws: Workspace, brief: Brief, problems: list[str], rejected: list[str] | None = None,
                         develop: dict | None = None) -> Path:
    if develop:
        rejected = None
    again = (["المالك رفض الصفحة السابقة بسبب (قراره 2026-11-13: رفضه بسببٍ أمرُ إعادتها إلى المصمّم)؛ يُرسل النص في المحادثة نفسها،",
              "والصفحة الجديدة تحلّ محلّ السابقة في `designer/` (المرفوضة محفوظة في `designer/rejected/`).", ""] if rejected else [])
    if develop:
        again = [f"المالك اختار السكتش {develop['sketch']} وطلب تطويره بصفحة حوله قبل بنائه (طلبه 2026-11-13)؛ يُرسل النص في المحادثة نفسها،",
                 "والصفحة الجديدة تحلّ محلّ السابقة في `designer/` (الأصل محفوظة في `designer/developed/`).", ""]
    text = "\n".join([
        f"# طلب صفحة السكتشات من المصمّم الخارجي: {brief.name_ar}" + (f" (بعد رفض {len(rejected)})" if rejected else "") + (f" (تطوير السكتش {develop['sketch']})" if develop else ""), "",
        *again,
        "هذا الطلب لا يذهب إلى نموذج الخط: تُرسله الجلسة إلى المصمّم الخارجي بأمر المالك، نصًّا وحده بلا ملفات.",
        "الاستلام في `designer/` من الإصدار: الصورة `sketches.jpg` (أو png) و`sketches.yaml`:", "",
        "```yaml", "image: sketches.jpg", "source: من أين جاءت الصفحة ومتى",
        "sketches:", "  - {id: 1, idea: فكرة السكتش في جملة}", "picks: [3, 7, 12]   # أقوى ثلاثة عند المصمّم، للاطلاع", "```", "",
        *(["## ما ينقص في الاستلام الحالي", *[f"- {p}" for p in problems], ""] if problems else []),
        "ثم أعد تشغيل: `uv run sima run <brief>` فتظهر الصفحة للمالك في المنصة ليختار.", "",
        SENT, "", sketch_prompt(brief, rejected, develop), "",
    ])
    return ws.write_request(REQ_SKETCHES, text)


def _rebuilt_lines(rebuilt: list[str] | None) -> list[str]:
    """سبب ردّ المالك للمتجه بنصّه، بلا تأويل: المرجع صورة السكتش نفسها، والعلاج عمل المصمّم."""
    if not rebuilt:
        return []
    earlier = ["وردّ قبله تسليمًا آخر لهذه الأسباب: " + "؛ ".join(f"«{r}»" for r in rebuilt[:-1]) + "."] if rebuilt[:-1] else []
    return [f"صاحب العلامة ردّ المتجه الذي سلّمتَه لهذا السكتش. سببه بنصّه: «{rebuilt[-1]}».", *earlier,
            "ارجع إلى صورة السكتش في صفحة السكتشات أعلاه وابنِ المتجه من جديد مطابقًا لهيئته المرسومة، ثم سلّم الملفات الخمسة كلها",
            "من جديد. المواصفات كما هي:", ""]


def vector_prompt(brief: Brief, sheet: Sheet, choice: dict, fonts: list[str], rebuilt: list[str] | None = None) -> str:
    n = choice["sketch"]
    idea = dict(sheet.sketches)[n]
    note = [f"ملاحظة صاحب العلامة على اختياره: {choice['note']}", ""] if choice.get("note") else []
    return "\n".join([
        *_rebuilt_lines(rebuilt),
        f"صاحب العلامة اختار السكتش رقم {n} من صفحة السكتشات أعلاه: «{idea}».", *note,
        "حوّله إلى شعار متجه نهائي. انقل الفكرة والبناء كما هما: المسموح تنظيف الهندسة فقط (نِسب وسماكات متسقة ومنحنيات نظيفة)،",
        "ولا تضف عنصرًا ولا تغيّر الفكرة. إن رأيت ضعفًا فاذكره في سطر بعد التسليم ولا تعالجه من عندك.", "",
        "سلّم شيفرة كل ملف كاملة في كتلة شيفرة مستقلة يسبقها اسمه:",
        f"1. `logo.svg`: الشعار الأساسي كاملًا (الرمز، ومعه الاسم «{mark_name(brief)}» محوّلًا إلى مسارات إن كان جزءًا منه).",
        "2. `icon.svg`: الرمز الصغير وحده في viewBox مربع، يُقرأ عند 16 بكسلًا.",
        "3. `motif.svg`: نمط هادئ مشتق من هندسة الشعار، يصلح خلفية أغلفة وورق رسمي.",
        "قيود الملفات الثلاثة: أشكال ومسارات فقط، لون واحد أسود #000000 على شفاف، بلا نص حي ولا تدرجات ولا فلاتر ولا صور ولا خطوط",
        "خارجية، وviewBox صريح، وأصغر سماكة في الرمز لا تقل عن 1.5 بكسل حين يُعرض بارتفاع 16.",
        "4. `direction.yaml`: اتجاه هوية واحد بهذه الصيغة بالضبط:", "",
        "```yaml", "name: اسم الاتجاه", "idea: فكرته في جملة",
        "colors: {paper: \"#RRGGBB\", ink: \"#RRGGBB\", brand: \"#RRGGBB\", accent: \"#RRGGBB\", neutral: \"#RRGGBB\",",
        "         success: \"#RRGGBB\", warning: \"#RRGGBB\", error: \"#RRGGBB\", info: \"#RRGGBB\"}",
        "accent_informational: false", "type:", "  heading: {font: اسم ملف الخط, weight: 700}", "  body: {font: اسم ملف الخط, weight: 400}",
        "  numerals: latn", "motif: {rule: أين يُستعمل النمط وأين لا يُستعمل}", "radius: 4", "```", "",
        "الخطوط من هذه القائمة وحدها (بأسماء ملفاتها): " + "، ".join(fonts) + ".",
        f"الألوان تطوير للوحة الموجز: ورق {brief.palette.paper}، حبر {brief.palette.ink}، علامة {brief.palette.brand}، "
        f"تمييز {brief.palette.accent}. تباين الحبر على الورق ولون العلامة على الورق لا يقل كلٌّ منهما عن 4.5:1 "
        "(لون العلامة يُستعمل نصًّا ورابطًا).",
        "5. `concept.yaml`: `name` (اسم الشعار في كلمتين)، `sentence` (فكرته في جملة)، `construction` (كيف بُني: الشبكة والسماكة).", "",
        "ثم سطران: ماذا نظّفت ولماذا، وأقرب قراءة خاطئة للشعار.",
    ])


def write_vector_request(ws: Workspace, brief: Brief, sheet: Sheet, choice: dict, problems: list[str], fonts: list[str],
                         rebuilt: list[str] | None = None) -> Path:
    text = "\n".join([
        f"# طلب بناء السكتش المختار متجهًا من المصمّم الخارجي: {brief.name_ar}", "",
        f"المالك اختار السكتش {choice['sketch']} في المنصة، واختياره أمرُ إرسال هذا الطلب في المحادثة نفسها التي رُسمت فيها",
        "الصفحة (ليرى المصمّم السكتش). يُرسل النص وحده.",
        *(["المالك ردّ المتجه المستلَم بسبب، وردّه أمرُ إعادة السكتش نفسه إلى المصمّم بسببه بنصّه (قراره 2026-11-13)؛ التسليم المردود",
           "محفوظ في `designer/rebuilt/`."] if rebuilt else []),
        "الاستلام: تُحفظ الملفات الخمسة في مجلد، ثم `uv run sima designer <brief> --intake <المجلد>` يكتب بيان الاعتماد ببصماته",
        "في `designer/adopt.yaml`. لا يُعدَّل في الملفات شيء: ما لا يجتاز الفحص يُعاد إلى المصمّم بسببه.", "",
        *(["## ما ردّه الفحص في التسليم الحالي", *[f"- {p}" for p in problems], ""] if problems else []),
        SENT, "", vector_prompt(brief, sheet, choice, fonts, rebuilt), "",
    ])
    return ws.write_request(REQ_VECTOR, text)


def fix_prompt(findings: list[str], min_px: int) -> str:
    """نص ما ردّه الفحص كما قيس، بلا اقتراح علاج: العلاج قرار المصمّم ضمن الفكرة المختارة."""
    lines, files = [], set()
    for f in findings:
        key, _, why = f.partition(": ")
        files.add(FILE_OF.get(key, key))
        lines.append(f"- `{FILE_OF.get(key, key)}`: {why}")
    limits = []
    if any(name.endswith(".svg") for name in files):
        limits.append(f"القيد كما في الطلب: أصغر سماكة في الرمز لا تقل عن 1.5 بكسل في كل موضع حين يُعرض بارتفاع {min_px} بكسلًا.")
    if FILE_OF["direction"] in files:
        limits.append("الحد المذكور مع كل سبب هو ما يقيسه الفحص، وهو الملزم ولو ذُكر في الطلب السابق حدّ أدنى منه.")
    return "\n".join([
        "فحص القبول ردّ التسليم لهذه الأسباب كما قيست:", *lines, "", *limits,
        "صحّح الملف المردود وحده وأعد تسليم شيفرته كاملة في كتلة شيفرة مستقلة يسبقها اسمه، بقيود الملفات نفسها.",
        "لا تغيّر الفكرة ولا الملفات التي لم تُردّ. ثم سطر واحد: ماذا غيّرت.",
    ])


def fix_round(ws: Workspace, digest: str, build_id: str) -> int:
    """رقم جولة التصحيح لهذا التسليم في البناء الجاري: كل بيان اعتماد مردود يُعدّ مرة واحدة ببصمته، واختيار جديد أو ردّ المالك
    للمتجه بناءٌ جديد يبدأ العدّ من أوله (ب4: كان العدّاد للإصدار كله أبدًا). علامة بلا بناء لا تُحسب على هذا البناء."""
    marker = ws.read_marker(FIX_MARKER)
    seen = [str(d) for d in marker.get("digests", [])] if marker.get("build") == build_id else []
    if digest not in seen:
        seen.append(digest)
        ws.mark_done(FIX_MARKER, {"build": build_id, "digests": seen})
    return len(seen)


def write_fix_request(ws: Workspace, brief: Brief, findings: list[str], min_px: int, round_no: int) -> Path:
    text = "\n".join([
        f"# طلب تصحيح من المصمّم الخارجي: {brief.name_ar} (الجولة {round_no} من {FIX_ROUNDS})", "",
        "فحص سِمة ردّ التسليم. بقرار المالك (2026-11-13) يعود ما يردّه الفحص إلى المصمّم بسببه دون سؤاله؛ يُرسل النص وحده في",
        "المحادثة نفسها. الاستلام كما في طلب المتجه: الملف المصحَّح يحلّ محلّ سابقه في مجلد التسليم والبقية كما هي، ثم",
        "`uv run sima designer <brief> --intake <المجلد>`. لا يُعدَّل في الملفات شيء هنا.", "",
        SENT, "", fix_prompt(findings, min_px), "",
    ])
    return ws.write_request(REQ_FIX, text)
