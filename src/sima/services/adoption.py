"""بيان التبنّي: ما في دليل الهوية، وما طُبّق منه في المشروع المستلم آليًا، وما تبقّى على جلسة المشروع (قرار المالك 2026-11-14).

التسليم كان يطبّق الرمز والرموز اللونية والورقة ويكتب الدليل مرجعًا، ثم تخمّن جلسة المشروع ما الباقي (ما الذي لم يُطبَّق؟ أي
ملف يقابل أي متغير؟ كيف تُضمَّن الحركة؟). هنا يُكتب `identity/ADOPTION.yaml` في المشروع: أقسام الدليل بملفاتها وحالتها، وجدول مطابقة
المتغيرات (اسم المتغير ← دور الهوية ← قيمتا النهار والليل)، وفحوص تُقاس على شجرة المشروع نفسها فتُظهر الفجوة بإجراء لكل واحدة،
ومعه `motion.css` جاهز للتضمين. دوال صافية بلا آثار جانبية؛ المتغيرات اللونية وحدها تُفحص قيمها، والفجوات الأخرى فحوص وجود.

الأيقونات والنمط والشاشات (أمر المالك 2026-11-17 بعد «مسك» v5: مرّت الفجوات ولم يتغيّر في التطبيق إلا الشعار واللون): كل أيقونة
ونمط يُعرف بمساره المرسوم، فيُعدّ مستعملًا إن رسمته الواجهة نصًّا أو ذكرت اسم نسخة منه؛ والنمط في شاشة الافتتاح وحدها لا يكفي.
والتسليم لا يصيّر تطبيق المشروع، فتطبيق الشاشات يُقاس بوجود اختبار في المشروع يقارن صفحاته بـ`identity/screens`.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

from . import apply_identity as roles_map

FILE_NAME = "ADOPTION.yaml"
MOTION_FILE = "motion.css"
MOTION_CLASS = "sima-mark-intro"
SCREENS_REF = "identity/screens"  # ما يذكره اختبار المشروع الذي يقارن صفحاته بشاشات الدليل
_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
_PATH_D = re.compile(r'\bd="([^"]+)"')
_UI_TEXT = (".css", ".scss", ".vue", ".ts", ".js", ".html")

# أقسام الدليل: المعرّف والعنوان وبادئات ملفاتها تحت identity/ وما يطبّقه التسليم نفسه (applied) أو يسلّمه مرجعًا (provided)
SECTIONS: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("strategy", "المنصة الاستراتيجية (الشخصية والنبرة واتجاه الصورة)", ("STRATEGY.md",), "provided"),
    ("color", "الألوان والأدوار في الوضعين", ("tokens/tokens.css",), "applied"),
    ("type", "الخط", ("fonts/",), "provided"),
    ("pattern", "النمط", ("patterns/",), "provided"),
    ("icons", "مجموعة الأيقونات", ("icons/",), "provided"),
    ("applications", "الهوية في الاستعمال: التطبيقات والشاشات", ("applications/", "screens/"), "provided"),
    ("motion", "الحركة: ظهور الرمز", ("motion/", MOTION_FILE), "provided"),
    ("tokens", "tokens بصيغها", ("tokens/",), "provided"),
    ("book", "دليل الهوية وعرض الكشف", ("brand-book.", "reveal."), "provided"),
)


class RepoFiles(Protocol):
    def read_text(self, rel: str) -> str | None: ...
    def walk(self, sub: str = "") -> list[str]: ...


@dataclass(frozen=True)
class Check:
    id: str
    section: str
    ok: bool
    detail: str
    action: str = ""  # ما تفعله جلسة المشروع إن لم يمرّ الفحص


@dataclass(frozen=True)
class Adoption:
    yaml_text: str
    motion_css: str
    checks: tuple[Check, ...]

    @property
    def gaps(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if not c.ok)

    def summary(self) -> str:
        gaps = self.gaps
        head = f"{FILE_NAME}: {len(self.checks) - len(gaps)} من {len(self.checks)} فحصًا يمرّ على مشروعك"
        if not gaps:
            return head + "."
        return head + "؛ الفجوات: " + "، ".join(f"{g.id} ({g.detail})" for g in gaps) + ". الإجراء لكل فجوة في الملف."


def motion_css(html: str) -> str:
    """قواعد ظهور الرمز من `motion/mark-intro.html`: المدة والمنحنى والتتابع وkeyframes وإلغاؤها عند تقليل الحركة، بصنف قابل للتضمين."""
    m = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
    if not m:
        return ""
    keep = [ln for ln in m.group(1).splitlines()
            if ".mark>*" in ln or "@keyframes" in ln or "prefers-reduced-motion" in ln]
    if not keep:
        return ""
    body = "\n".join(keep).replace(".mark>*", f".{MOTION_CLASS}>*")
    return ("/* ظهور الرمز من هوية سِمة: ضع الصنف " + MOTION_CLASS + " على عنصر svg يضم أجزاء الرمز، وأعطِ كل جزء --i (0 فصاعدًا).\n"
            "   600ms وتتابع 90ms لكل جزء، وتُلغى الحركة عند prefers-reduced-motion. مولَّد؛ لا يُعدَّل يدويًا. */\n" + body + "\n")


def token_map(rules: tuple[roles_map.Rule, ...], roles: Mapping[str, Mapping[str, str]], slug: str) -> list[dict]:
    """جدول المطابقة: متغير التطبيق ← دور الهوية ← متغير الهوية وقيمتا النهار والليل (الغائب يُترك بقيمة التطبيق)."""
    rows: list[dict] = []
    for r in rules:
        row: dict = {"app_var": f"--{r.var}"}
        for mode in roles_map.MODES:
            role = getattr(r, mode)
            if role:
                value = roles[mode].get(role)
                row[mode] = {"role": role, "var": f"--{slug}-{role}", "value": roles_map._value(r, role, roles[mode], mode)
                             if value is not None else None}
            else:
                row[mode] = "يُترك بقيمة التطبيق"
        if r.times != 1:
            row["times"] = r.times
        rows.append(row)
    return rows


def _first_value(css: str, var: str, depth: int = 4) -> str | None:
    m = re.search(rf"--{re.escape(var)}\s*:\s*([^;]+);", css)
    if not m:
        return None
    value = m.group(1).strip().lower()
    pair = roles_map.light_dark(value)  # تعريف بقيمتين: النهارية أولاهما
    value = pair[0] if pair else value
    ref = re.fullmatch(r"var\(\s*--([a-z0-9_-]+)\s*\)", value)  # إحالة (`var(--day-ink)`): قيمة المتغير المحال إليه أولًا
    return (_first_value(css, ref.group(1), depth - 1) or value) if ref and depth else value


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def signature(svg: str) -> str:
    """بصمة أصل مرسوم: أطول مسار فيه بعد توحيد الفراغات؛ بها يُعرف في شجرة المشروع ولو نُسخ باسم آخر أو رُسم داخل مكوّن."""
    paths = [_norm(d) for d in _PATH_D.findall(svg)]
    return max(paths, key=len) if paths else ""


def _uses(sig: str, ui: Mapping[str, str], copies: Mapping[str, str]) -> list[str]:
    """ملفات الواجهة التي تستعمل الأصل: ترسم مساره نصًّا، أو تذكر اسم ملف svg في المشروع يحمل المسار نفسه، أو تذكر اسمه
    بلا لاحقة بين علامتي اقتباس ومجلد نسخته مستورد جملةً (`icons/*.svg`) كما يفعل مكوّن أيقونات يأخذ الاسم خاصية."""
    if not sig:
        return []
    needles: list[str] = []
    for rel in (r for r, text in copies.items() if sig in text):
        folder, _, name = rel.rpartition("/")
        needles.append(name)
        if any(folder.rsplit("/", 1)[-1] + "/*.svg" in text for text in ui.values()):
            stem = name.removesuffix(".svg")
            needles += [f'"{stem}"', f"'{stem}'"]
    return sorted(rel for rel, text in ui.items() if sig in text or any(n in text for n in needles))


def _asset_checks(identity_dir: Path, files: RepoFiles, ui_raw: Mapping[str, str], tests: list[str]) -> list[Check]:
    """الأيقونات والنمط والشاشات: استعمال يُقاس على شجرة المشروع، لا وجود ملفات المرجع."""
    out: list[Check] = []
    ui = {rel: _norm(text) for rel, text in ui_raw.items()}
    copies = {rel: _norm(files.read_text(rel) or "")
              for rel in files.walk("frontend") + files.walk("templates") if rel.endswith(".svg")}

    def sigs(sub: str) -> list[tuple[str, str]]:
        folder = identity_dir / sub
        found = sorted(folder.glob("*.svg")) if folder.is_dir() else []
        named = [(p.stem, signature(p.read_text(encoding="utf-8"))) for p in found]
        return [(name, sig) for name, sig in named if sig]  # أصل بلا مسار لا يُقاس استعماله فلا يُحكم عليه

    icons = sigs("icons")
    if icons:
        unused = [name for name, sig in icons if not _uses(sig, ui, copies)]
        detail = f"{len(icons) - len(unused)} من {len(icons)} أيقونة مستعملة في الواجهة"
        out.append(Check("icons-used", "icons", not unused, detail + ("" if not unused else "؛ غير المستعملة: " + "، ".join(unused)),
                         "" if not unused else "استعمل أيقونات identity/icons كما هي حيث تعرض الواجهة معناها؛ ما لا موضع له في "
                         "التطبيق يُذكر للمالك ولا يُحشر."))
    motifs = sigs("patterns")
    if motifs:
        used = sorted({rel for _, sig in motifs for rel in _uses(sig, ui, copies)})
        pages = [rel for rel in used if "splash" not in rel.lower()]
        detail = ("النمط مستعمل في " + "، ".join(pages[:4]) if pages
                  else "النمط في شاشة الافتتاح وحدها" if used else "النمط غير مستعمل في الواجهة")
        out.append(Check("pattern-used", "pattern", bool(pages), detail,
                         "" if pages else "ضع identity/patterns/motif-*.svg في الصفحات حيث تضعه شاشات identity/screens."))
    screens_dir = identity_dir / "screens"
    screens = sorted(p.name for p in screens_dir.glob("*.html")) if screens_dir.is_dir() else []
    if screens:
        compared = any(SCREENS_REF in (files.read_text(rel) or "") for rel in tests)
        out.append(Check("screens-compared", "applications", compared,
                         "اختبار يقارن صفحات المشروع بشاشات الدليل " + ("موجود" if compared else "غير موجود"),
                         "" if compared else "ابنِ الصفحات على " + "، ".join(f"screens/{n}" for n in screens)
                         + f" واكتب اختبارًا يصيّرها بمقاس كل شاشة ويقارنها بصورتها (يذكر {SCREENS_REF})."))
    return out


def _checks(slug: str, rules: tuple[roles_map.Rule, ...], roles: Mapping[str, Mapping[str, str]],
            app_tokens: str | None, files: RepoFiles, identity_dir: Path) -> list[Check]:
    out: list[Check] = []
    # ١) تطابق الألوان النهارية في رموز التطبيق مع الهوية (الليلية يطبّقها apply_identity ولا يُعاد فحصها هنا)
    if app_tokens is None:
        out.append(Check("color-parity", "color", False, "لا frontend/src/styles/tokens.css في المشروع",
                         "أنشئ tokens.css برموز الهوية من token_map ثم أعد التسليم."))
    else:
        bad = []
        for r in rules:
            if not r.light or r.light not in roles["light"] or not _HEX.fullmatch(roles["light"][r.light]):
                continue
            want = roles["light"][r.light].lower()
            got = _first_value(app_tokens, r.var)
            if got != want:
                bad.append(f"--{r.var}: {got or 'غائب'} بدل {want}")
        out.append(Check("color-parity", "color", not bad, "كل المتغيرات اللونية النهارية مطابقة" if not bad else "؛ ".join(bad[:4]),
                         "" if not bad else "طابق القيم مع token_map (لا تُعدَّل في الواجهة؛ التسليم يطبّقها)."))
    # ٢) الخط: عائلة العناوين مذكورة في أنماط المشروع
    heading = roles["light"].get("font-heading", "")
    family = re.match(r'\s*"?([^",]+)"?', heading)
    if family:
        name = family.group(1).strip()
        styles = [rel for rel in files.walk("frontend/src") if rel.endswith((".css", ".scss", ".vue"))]
        found = any(name in (files.read_text(rel) or "") for rel in styles)
        out.append(Check("font-family", "type", found, f"عائلة {name} " + ("مذكورة في أنماط المشروع" if found else "غير مذكورة في أنماط المشروع"),
                         "" if found else f"أضف @font-face أو استيرادًا للخط {name} من identity/fonts واجعله عائلة العناوين والنص."))
    # ٣) الحركة والشرائح والافتتاح والاختبار: فحوص وجود على الشجرة
    src_files = files.walk("frontend/src") + files.walk("templates")
    text_of = {rel: files.read_text(rel) or "" for rel in src_files if rel.endswith(_UI_TEXT)}
    has_motion = any(MOTION_CLASS in t or "sima-rise" in t for t in text_of.values())
    out.append(Check("motion-included", "motion", has_motion, "ظهور الرمز " + ("مضمَّن" if has_motion else "غير مضمَّن في الواجهة"),
                     "" if has_motion else f"استورد identity/{MOTION_FILE} وطبّق الصنف {MOTION_CLASS} على الرمز عند أول ظهور."))
    all_files = files.walk()
    for cid, section, needle, label, action in (
        ("slide-templates", "applications", "slide", "قوالب الشرائح", "ابنِ قالب شرائح 16:9 من identity/applications/slide-*.svg."),
        ("splash-screen", "applications", "splash", "شاشة الافتتاح", "ابنِ شاشة افتتاح من identity/applications/app-splash.svg."),
    ):
        found = any(needle in rel.lower() for rel in all_files if not rel.startswith("brand/"))  # حيثما بناها المشروع، لا مرجع الهوية
        out.append(Check(cid, section, found, label + (" موجودة" if found else " غير موجودة في المشروع"), "" if found else action))
    tests = [rel for rel in all_files if re.search(r"(^|/)(tests?|__tests__)/|\.(spec|test)\.[jt]s$|(^|/)test_[^/]+\.py$", rel)]
    guarded = any(FILE_NAME in (files.read_text(rel) or "") for rel in tests)
    out.append(Check("token-parity-test", "tokens", guarded, "اختبار تطابق الرموز مع " + FILE_NAME + (" موجود" if guarded else " غير موجود"),
                     "" if guarded else f"اكتب اختبارًا يقرأ token_map من {FILE_NAME} ويطابقه مع tokens.css."))
    # ٤) الأيقونات والنمط والشاشات: استعمالها في الواجهة لا وجودها مرجعًا
    out.extend(_asset_checks(identity_dir, files, text_of, tests))
    return out


def _sections(identity_dir: Path, extra: tuple[str, ...]) -> list[dict]:
    rels = sorted({p.relative_to(identity_dir).as_posix() for p in identity_dir.rglob("*") if p.is_file() and p.suffix != ".json"}
                  | set(extra))
    out = []
    for sid, title, prefixes, status in SECTIONS:
        mine = [r for r in rels if any(r.startswith(pre) for pre in prefixes)]
        out.append({"id": sid, "title": title, "status": status, "files": mine})
    return out


def build(slug: str, version: int, concept_id: str, identity_dir: Path, rules: tuple[roles_map.Rule, ...],
          roles: Mapping[str, Mapping[str, str]], app_tokens: str | None, files: RepoFiles) -> Adoption:
    motion_src = identity_dir / "motion" / "mark-intro.html"
    motion = motion_css(motion_src.read_text(encoding="utf-8")) if motion_src.is_file() else ""
    checks = tuple(_checks(slug, rules, roles, app_tokens, files, identity_dir))
    doc = {
        "release": f"{slug}/v{version}",
        "concept": concept_id,
        "purpose": "ما في دليل الهوية، وما طُبّق منه آليًا في هذا المشروع، وما تبقّى على جلسة المشروع. مولَّد من سِمة؛ لا يُعدَّل يدويًا.",
        "applied_by_delivery": ["الرمز والقفل والأيقونات العامة وmanifest", "رموز التطبيق اللونية والأبعاد حسب token_map، نهارًا وليلًا",
                                "الورقة المطبوعة (apply_paper) حيث رُسمت خريطتها"],
        "limits": ["قيم الوضع الليلي يطبّقها التسليم ولا يعيد فحصها هنا؛ فحص color-parity للنهار وحده",
                   "الفحوص الأخرى فحوص وجود لا جودة: وجودها لا يعني أنها مطابقة لتصميم الدليل",
                   "الأيقونات والنمط يُقاس استعمالهما لا موضعهما، والشاشات يُقاس وجود اختبار مقارنتها لا نتيجته: التسليم لا يصيّر التطبيق"],
        "sections": _sections(identity_dir, (MOTION_FILE,) if motion else ()),
        "token_map": token_map(rules, roles, slug),
        "checks": [{"id": c.id, "section": c.section, "ok": c.ok, "detail": c.detail, **({"action": c.action} if c.action else {})}
                   for c in checks],
        "gaps": [c.id for c in checks if not c.ok],
    }
    text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=120)
    return Adoption(text, motion, checks)
