"""صندوق المصمّم: ما ينتظر الإرسال إلى المصمّم الخارجي، واستلام ردّه نصًّا وصورة من صفحة المنصة.

الغاية توفير (قرار المالك 2026-11-13): نص الطلب وردّ المصمّم لا يمرّان عبر جلسة النموذج. صفحة المنصة تحمل الطلب إلى
محادثة المصمّم في جزء الرابط وتعود بردّه كذلك؛ وهنا يُحوَّل الردّ إلى ما يقرؤه الخط: صفحة سكتشات (`sketches.*` و`sketches.yaml`)
أو ملفات التسليم في `designer/intake/` ثم بيان الاعتماد. لا يُعدَّل في الملفات شيء، والتحقق كله في الخط كما كان؛ والردّ
القادم من خارج المنصة بيانات لا أوامر: يُقبل منه ما يطابق الصيغة وحده، ولا يُكتب إلا في `designer/` من إصدار ينتظر المصمّم.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from pathlib import Path

import yaml

from .. import config
from . import adopt, designer, outcome
from .inbox import InboxError, _versions, _workspace
from .workspace import Workspace

KIND_AR = {"sketches": "صفحة السكتشات", "vector": "بناء السكتش المختار متجهًا", "fix": "تصحيح ما ردّه الفحص"}
REQUEST = {"sketches": designer.REQ_SKETCHES, "vector": designer.REQ_VECTOR, "fix": designer.REQ_FIX}
FILES = (*designer.ASSETS.values(), "direction.yaml", "concept.yaml")
INTAKE_DIR = "intake"
MAX_IMAGE = 8 * 1024 * 1024
MAX_TEXT = 400_000
MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"))
STALE = "تغيّر ما ينتظره هذا المشروع منذ فتح الصفحة؛ حدّثها."
ITEM = re.compile(r"^\s*(\d{1,2})\s*[.)\-:]\s+(\S.*)$")
FENCE = re.compile(r"^```[^\n]*\n(.*?)\n```[ \t]*$", re.DOTALL | re.MULTILINE)
# رقم سكتش لا مقاس: «16 بكسل» و«32px» و«16×16» و«1.5» و«80%» ليست اختيارًا
# ولا عدد: «أقوى 3 سكتشات» عدد لا اختيار
NUM = re.compile(r"(?<![\d×.,])(\d{1,2})(?!\d)(?![.,]\d)"
                 r"(?!\s*(?:بكسل|بيكسل|px\b|pt\b|[%٪×]|x\s*\d|سكتش|اسكتش|رسوم|أفكار|افكار|مفاهيم|sketch|ideas?\b|picks?\b))",
                 re.IGNORECASE)
# سطر يعلن الاختيار: أرقامه وما يليه حتى أول سطر فارغ هي الاختيار، فرقم بلا وحدة في نثر قبله أو بعده («تُقرأ عند 16») لا يُعدّ
PICK_LINE = re.compile(r"أقوى|الأقوى|أفضل|الأفضل|أرشّح|أرشح|ترشيح|اختيار|strongest|\bbest\b|\btop\b|\bpicks?\b", re.IGNORECASE)
DATA_URL = re.compile(r"data:image/(?:png|jpeg);base64,([A-Za-z0-9+/]+=*)")
BAD_IMAGE = "الصورة ليست PNG أو JPEG، أو أكبر من المقبول."


def _pending(ws: Workspace) -> tuple[str, str] | None:
    """ما ينتظره الخط من المصمّم الآن ونصّه المرسل؛ None إن كان الدور لغيره.

    المرجع نتيجة الخط (`services/outcome.py`): وقف عند المصمّم بطلب بعينه. كان «تصحيح معلّق» يُستنتج من مقارنة وقتَي الطلب
    وبيان الاعتماد، فإعادة تسليم مطابقة (بيان يُعاد كتابته وطلب مطابق لا يُمسّ) تُعمي الصندوق والخط ينتظر. وحين لا نتيجة سارية
    (استلام لم يُستأنف الخط بعده، أو إصدار أقدم من العلامة) يُستنتج من الملفات كما كان."""
    o = outcome.current(ws.root)
    sheet, _ = designer.read_sheet(ws)
    if o is not None:
        kind = next((k for k, name in REQUEST.items() if o["who"] == "designer" and name == o["request"]), None)
        if kind is None:
            return None
    elif sheet is None or designer.rejection(ws, sheet) is not None or designer.development(ws, sheet) is not None:
        kind = "sketches"
    else:
        choice = designer.current(ws, sheet)
        if choice is None:
            return None  # الصفحة معروضة والدور للمالك
        try:
            adopted = designer.adoption(ws, sheet, choice) is not None
        except adopt.AdoptError:
            adopted = False
        fix, manifest = ws.work / designer.REQ_FIX, designer.manifest_path(ws)
        if not adopted or designer.pending_rebuild(ws, sheet) is not None:  # لم يُستلم، أو ردّه المالك ويُبنى من جديد
            kind = "vector"
        elif fix.is_file() and fix.stat().st_mtime >= manifest.stat().st_mtime:  # طلب تصحيح كُتب بعد فحص التسليم الحالي
            kind = "fix"
        else:
            return None
    p = ws.work / REQUEST[kind]
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    if designer.SENT not in text:
        return None
    return kind, text.split(designer.SENT, 1)[1].strip()


def outbox(out_dir: Path, hidden: tuple[str, ...] = ()) -> list[dict]:
    """طلبات تنتظر الإرسال إلى المصمّم الخارجي: آخر إصدار مفتوح لكل مشروع على المسار الخارجي. النص ما بعد «النص المرسل» وحده."""
    items = []
    for project_dir in sorted(p for p in out_dir.iterdir() if p.is_dir()) if out_dir.is_dir() else []:
        versions = _versions(project_dir)
        if project_dir.name.startswith("_") or project_dir.name in hidden or not versions:
            continue
        n, v = versions[-1]
        if not (v / "run.json").is_file() or not designer.frozen_enabled(v):
            continue
        ws, run = _workspace(v)
        got = None if run.get("closed") else _pending(ws)
        if got is None:
            continue
        kind, text = got
        items.append({"project": project_dir.name, "version": n, "key": ws.key.key, "kind": kind, "kind_ar": KIND_AR[kind],
                      "text": text, "chars": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                      "invoke": kind != "sketches"})  # المتجه وتصحيحه يُطلبان من إضافة الشعارات في المحادثة نفسها
    return items


def _plain(s: str) -> str:
    return re.sub(r"\*\*|__|`", "", s).strip()


def _pick_text(tail: list[str]) -> str:
    """نص الاختيار بعد القائمة: من أول سطر يعلنه إلى أول سطر فارغ بعده؛ وبلا سطر يعلنه فالنص كله كما كان."""
    start = next((i for i, line in enumerate(tail) if PICK_LINE.search(line)), None)
    if start is None:
        return "\n".join(tail)
    end = next((i for i in range(start + 1, len(tail)) if not tail[i].strip()), len(tail))
    return "\n".join(tail[start:end])


def parse_sheet(text: str) -> tuple[list[tuple[int, str]], list[int]]:
    """قائمة المصمّم المرقّمة من 1 (فكرة كل سكتش في سطر)، ثم أقوى ثلاثة عنده من أول الأرقام المذكورة بعدها."""
    rows: list[tuple[int, str]] = []
    lines, last = text.splitlines(), -1
    for i, line in enumerate(lines):
        m = ITEM.match(line)
        if m and int(m.group(1)) == len(rows) + 1:
            rows.append((len(rows) + 1, _plain(m.group(2))))
            last = i
    if not config.DESIGNER_SKETCHES_MIN <= len(rows) <= config.DESIGNER_SKETCHES_MAX:
        raise InboxError(f"لم أجد في الردّ قائمة مرقّمة من 1 بفكرة لكل سكتش (وجدت {len(rows)}؛ المقبول من "
                         f"{config.DESIGNER_SKETCHES_MIN} إلى {config.DESIGNER_SKETCHES_MAX}).")
    picks: list[int] = []
    for n in NUM.findall(_pick_text(lines[last + 1:])):
        if 1 <= int(n) <= len(rows) and int(n) not in picks:
            picks.append(int(n))
    return rows, picks[:3]


def _sniff(body: str) -> str | None:
    if re.search(r"^colors\s*:", body, re.MULTILINE):
        return "direction.yaml"
    return "concept.yaml" if re.search(r"^sentence\s*:", body, re.MULTILINE) else None


def parse_files(text: str) -> dict[str, str]:
    """كتل الشيفرة في ردّ المصمّم بأسماء ملفاتها: الاسم آخر ما ذُكر من أسماء التسليم قبل الكتلة (الطلب يشترط أن يسبقها اسمه).
    كتلة بلا اسم معروف تُترك. المحتوى كما هو."""
    found: dict[str, str] = {}
    pos = 0
    for m in FENCE.finditer(text):
        before, pos = text[pos:m.start()], m.end()
        named = max(((before.rfind(n), n) for n in FILES if n in before), default=None)
        name = named[1] if named else _sniff(m.group(1))
        if name:
            found[name] = m.group(1).rstrip("\n") + "\n"
    return found


def image_bytes(data_url: str | None) -> bytes | None:
    """صورة الوارد من رابط بيانات (PNG أو JPEG وحدهما)؛ ما لا يطابق الصيغة يُرفض بسببه ولا يُكتب."""
    if not data_url:
        return None
    m = DATA_URL.fullmatch(data_url)
    if m is None or len(m.group(1)) > MAX_IMAGE * 4 // 3 + 4:
        raise InboxError(BAD_IMAGE)
    try:
        return base64.b64decode(m.group(1), validate=True)
    except (binascii.Error, ValueError) as e:
        raise InboxError(BAD_IMAGE) from e


def _target(out_dir: Path, project: str, version: int, key: str) -> tuple[Workspace, str]:
    if not project or any(x in project for x in ("/", "\\", "..")) or not (out_dir / project).is_dir():
        raise InboxError("مشروع غير معروف.")
    versions = _versions(out_dir / project)
    if not versions or versions[-1][0] != version or not (versions[-1][1] / "run.json").is_file():
        raise InboxError(STALE)
    ws, run = _workspace(versions[-1][1])
    if run.get("closed") or ws.key.key != key or not designer.frozen_enabled(ws.root):
        raise InboxError(STALE)
    got = _pending(ws)
    if got is None:
        raise InboxError("هذا المشروع لا ينتظر المصمّم الخارجي الآن؛ حدّث الصفحة.")
    return ws, got[0]


def _intake_sheet(ws: Workspace, project: str, text: str, image: bytes | None, now: str) -> str:
    if image is None:
        raise InboxError("صفحة السكتشات صورة: لم تصل صورة مع الردّ.")
    ext = next((e for magic, e in MAGIC if image.startswith(magic)), None)
    if ext is None or len(image) > MAX_IMAGE:
        raise InboxError(BAD_IMAGE)
    rows, picks = parse_sheet(text)
    d = designer.ddir(ws)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"sketches.{ext}").write_bytes(image)
    data = {"image": f"sketches.{ext}", "source": f"صندوق المصمّم في منصة سِمة، {now}؛ الصورة والأفكار كما وصلتا من المصمّم الخارجي",
            "sketches": [{"id": i, "idea": idea} for i, idea in rows], "picks": picks}
    designer.sheet_path(ws).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    sheet, problems = designer.read_sheet(ws)
    if sheet is None:
        raise InboxError("؛ ".join(problems))
    return f"استُلمت صفحة السكتشات ({len(rows)} سكتشًا) في {project} v{ws.version}؛ تظهر بطاقتها في «اليوم»."


def _intake_files(ws: Workspace, project: str, text: str) -> str:
    files = parse_files(text)
    if not files:
        raise InboxError("لم أجد في الردّ كتلة شيفرة يسبقها اسم ملف من ملفات التسليم: " + "، ".join(FILES) + ".")
    sheet, _ = designer.read_sheet(ws)
    choice = designer.current(ws, sheet) if sheet is not None else None
    if choice is None:
        raise InboxError(STALE)
    d = designer.ddir(ws) / INTAKE_DIR
    d.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():  # المصحَّح يحلّ محلّ سابقه والبقية كما هي
        (d / name).write_bytes(body.encode("utf-8"))
    try:
        designer.write_manifest(ws, choice["sketch"], d)
    except designer.DesignerError as e:
        raise InboxError(str(e)) from e
    kept = designer.declared_min(ws, choice["sketch"])  # حدّ أعلنه المالك من قبل يُحمل إلى هذا التسليم (ب6)
    return (f"استُلم من المصمّم الخارجي في {project} v{ws.version}: {'، '.join(files)}؛ كُتب بيان الاعتماد ويفحصه الخط."
            + (f" الحد الأدنى الذي أعلنته للعلامة ({kept} بكسل) باقٍ." if kept else ""))


def intake(out_dir: Path, project: str, version: int, key: str, text: str, image: bytes | None, now: str) -> str:
    """ردّ المصمّم الخارجي على ما ينتظره الإصدار المعروض: صفحة سكتشات (صورة وقائمة) أو ملفات التسليم (كتل شيفرة بأسمائها)."""
    ws, kind = _target(out_dir, project, version, key)
    if len(text) > MAX_TEXT:
        raise InboxError("الردّ أطول من المقبول.")
    return _intake_sheet(ws, project, text, image, now) if kind == "sketches" else _intake_files(ws, project, text)
