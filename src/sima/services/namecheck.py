"""خدمة التحقق من توافر الاسم: قائمة تحقق عربية بروابط السجلات الرسمية، وقراءة/كتابة سجلّ المالك.

لا اتصال شبكي هنا: الروابط تُكتب للمالك ليفحصها بنفسه ثم يسجّل النتيجة بأمر `sima name-check`.
"""
from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

import yaml

from ..domain import Brief
from ..domain.namecheck import NAME_STATUS_AR, NameCheck, NameStatus
from .workspace import Workspace

# (التسمية، قالب الرابط مع {q} للاسم مرمَّزًا، ملاحظة)
NAME_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("قاعدة WIPO العالمية للعلامات (تضم سجل قطر)", "https://branddb.wipo.int/en/quicksearch?by=brandName&v={q}", "ابحث بالعربية وباللاتينية ({q})."),
    ("وزارة التجارة والصناعة القطرية: خدمات العلامات التجارية", "https://www.moci.gov.qa/", "الاستعلام عن العلامة والاسم التجاري عبر بوابة الخدمات الإلكترونية."),
    ("سجل العلامات الخليجي الموحّد (GCC TM)", "https://www.gccpo.org/", "فحص الامتداد الخليجي إن كان مقصودًا."),
    ("نطاقات .qa (سجل قطر للنطاقات)", "https://www.domains.qa/", "تحقق من {q}.qa و{q}.com.qa أو ما يقابلها لاتينيًا."),
    ("متجر App Store", "https://www.apple.com/app-store/", "ابحث عن الاسم داخل المتجر في فئة التعليم."),
    ("متجر Google Play", "https://play.google.com/store/search?q={q}&c=apps", ""),
    ("بحث عام", "https://duckduckgo.com/?q={q}", "تطبيقات أو منصات أو شركات بالاسم نفسه في القطاع نفسه."),
)
# مفاتيح قصيرة لمصادر NAME_SOURCES بترتيبها؛ تُسجَّل في name_check.yaml من بطاقة المنصة ومن `sima name-check --source`
SOURCE_KEYS = ("WIPO", "MOCI", "GCC", "QA-DOMAINS", "APPSTORE", "PLAY", "WEB")
MIN_NOTE = 3


def _latin(name: str) -> str:
    """تهجئة لاتينية تقريبية للاسم للبحث؛ المالك يصحّحها إن لزم."""
    table = {"أ": "a", "إ": "i", "آ": "a", "ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh",
             "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "q",
             "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y", "ى": "a", "ة": "a", "ء": "", "ؤ": "w", "ئ": "y"}
    return "".join(table.get(ch, ch) for ch in name if not ("ً" <= ch <= "ْ"))


def checklist_md(brief: Brief, existing: NameCheck | None = None) -> str:
    """نص قائمة التحقق (حتمي: لا تاريخ ولا عشوائية) يُكتب في NAME-CHECK.md."""
    name = brief.wordmark_text
    latin = brief.name_latin or _latin(name)  # التهجئة المعتمدة في الموجز تسبق التقريبية
    lines = [f"# التحقق من توافر الاسم: «{name}»", "",
             "الأداة لا تتصل بالشبكة. افحص المصادر التالية بنفسك ثم سجّل النتيجة بالأمر في الأسفل. لا تُبنى الحزمة قبل تسجيل «clear».", "",
             f"التهجئة اللاتينية المقترحة للبحث: {latin}", "",
             "## المصادر", ""]
    for i, (label, url, note) in enumerate(NAME_SOURCES, 1):
        link = url.replace("{q}", quote(name))
        lines.append(f"{i}. {label}: {link}" + (f" — {note.replace('{q}', latin)}" if note else ""))
    lines += ["", "## ما يُعدّ تعارضًا",
              "- علامة مسجّلة أو منشورة بالاسم نفسه أو بما يلتبس به في الفئة 41 (التعليم) أو 9/42 (البرمجيات) في قطر.",
              "- تطبيق أو منصة تعليمية نشطة بالاسم نفسه في قطر أو الخليج.",
              "- اسم تجاري مسجّل في وزارة التجارة والصناعة يلتبس به.",
              "- استعمال الاسم في قطاع آخر أو بلد آخر لا يُعدّ تعارضًا بذاته، لكنه يُدوَّن في الملاحظة.", "",
              "## تنبيه",
              "الكلمات العامة الوصفية تُحمى ضعيفًا كعلامة كلامية مجردة؛ قوة الحماية في الرسم (العلامة المصوَّرة) وفي الاسم المركّب الكامل.", "",
              "## تسجيل النتيجة", "```bash",
              'uv run sima name-check <brief> --status clear --source "WIPO" --source "MOCI" --note "لا تعارض في الفئة 41"',
              'uv run sima name-check <brief> --status conflict --source "WIPO" --note "علامة مطابقة رقم ..."',
              "```"]
    if existing is not None:
        lines += ["", f"الحالة المسجّلة: {NAME_STATUS_AR[existing.status]} ({existing.checked_at})" + (f" — {existing.note}" if existing.note else "")]
    return "\n".join(lines) + "\n"


def read_name_check(ws: Workspace) -> NameCheck | None:
    p = ws.name_check_path
    if not p.is_file():
        return None
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    try:
        return NameCheck(name=str(data["name"]), status=NameStatus(str(data["status"])), checked_at=str(data.get("checked_at", "")),
                         sources=tuple(str(s) for s in data.get("sources", []) or []), note=str(data.get("note", "")))
    except (KeyError, ValueError):
        return None


def write_name_check(ws: Workspace, nc: NameCheck) -> None:
    ws.name_check_path.write_text(yaml.safe_dump({
        "name": nc.name, "status": nc.status.value, "checked_at": nc.checked_at, "sources": list(nc.sources), "note": nc.note,
    }, allow_unicode=True, sort_keys=False), encoding="utf-8")


def result_problem(status: NameStatus, sources: list[str], note: str) -> str | None:
    """قواعد تسجيل نتيجة التحقق، واحدة لبطاقة المنصة ولأمر `sima name-check` (مراجعة 2026-11-14، ب14): المصادر من مفاتيحها
    المعروفة، و«متاح» بمصدر واحد على الأقل، و«متعارض» بملاحظة. تعيد نص المخالفة أو None."""
    if any(s not in SOURCE_KEYS for s in sources):
        return "مصدر غير معروف. المصادر: " + "، ".join(SOURCE_KEYS) + "."
    if status is NameStatus.CLEAR and not sources:
        return "«متاح» يحتاج مصدرًا واحدًا على الأقل فحصته بنفسك."
    if status is NameStatus.CONFLICT and len(note.strip()) < MIN_NOTE:
        return "«متعارض» يحتاج ملاحظة بما وجدت."
    return None


def record_name_check(ws: Workspace, brief: Brief, status: NameStatus, sources: list[str], note: str) -> NameCheck:
    nc = NameCheck(name=brief.wordmark_text, status=status, checked_at=datetime.now(UTC).isoformat(timespec="seconds"),
                   sources=tuple(sources), note=note)
    write_name_check(ws, nc)
    return nc
