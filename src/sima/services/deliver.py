"""خدمة التسليم: من حزمة معتمدة إلى خطة كتابة حتمية في مستودع Django + Vue، ثم بطاقة للمشغّل.

الخطة تُحسب بلا آثار جانبية (قابلة للاختبار)، والتنفيذ عبر منفذ DeliveryTarget (المحوّل يتعامل مع git والدفتر).
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from ..domain import Brief
from ..domain.delivery import DeliveryPlan, DeliveryReceipt, FileWrite, applied
from . import adoption, export
from . import apply_identity as roles_map
from .deliver_django import card_text_django, plan_delivery_django
from .workspace import Workspace

# ملفات الحزمة → مسارها في المستودع الهدف (frontend/public تُخدم تحت STATIC_URL عبر Vite)
PUBLIC_FILES = ("favicon.svg", "favicon.ico", "favicon-32.png", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "maskable-512.png")
BRAND_DIR = "brand"
TOKENS_PATH = "frontend/src/styles/tokens.css"  # رموز التطبيق المستلم؛ بند `tokens:` في deliver_targets.yaml يغيّره لهدفه
MARK_COMMENT_OLD = "الشعار ثابت في الوضعين: هو العلامة، لا يتبع السمة"
MARK_COMMENT_NEW = "الشعار: حبره لون العلامة على الفاتح وأبيض على الداكن، ولون التمييز ثابت (مولَّد بأداة سِمة)"
MARK_COMMENT_MONO = "الشعار: حبره لون العلامة على الفاتح وأبيض على الداكن؛ الرمز بلون واحد (مولَّد بأداة سِمة)"


class RepoFiles(Protocol):
    """ملفات شجرة المستودع الهدف للقراءة وحدها: نسخة على القرص (DirFiles) أو مرجع git بلا سحب (المحوّل)."""

    def read_text(self, rel: str) -> str | None: ...
    def walk(self, sub: str = "") -> list[str]: ...


PRUNED = frozenset({"node_modules", "dist", "build", "__pycache__", "venv"})  # ومعها كل مجلد يبدأ بنقطة
TEXT_MAX = 1_000_000  # ما فوقه لا يُقرأ نصًّا (صور وخطوط وملفات قفل كبيرة)


class DirFiles:
    """شجرة على القرص: الملف غير النصي أو الكبير يُقرأ None، والمشي يتجاوز مجلدات البناء والمجلدات المخفية."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def read_text(self, rel: str) -> str | None:
        p = self.root / rel
        if not p.is_file() or p.stat().st_size > TEXT_MAX:
            return None
        try:
            return p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return None

    def walk(self, sub: str = "") -> list[str]:
        base = self.root / sub if sub else self.root
        found: list[str] = []
        for folder, dirs, names in os.walk(base) if base.is_dir() else ():
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in PRUNED)
            found.extend((Path(folder) / n).relative_to(self.root).as_posix() for n in names)
        return sorted(found)


class DeliveryTarget(Protocol):
    """منفذ المستودع الهدف: دفتر بطاقات + git worktree. المحوّل الفعلي في adapters/ledger_runner.py."""

    def base_files(self) -> RepoFiles: ...  # شجرة الأساس الذي يُفتح منه فرع البطاقة (origin/main)، لنص البطاقة قبل وجود الفرع
    def new_card(self, title: str, body: str, success: str) -> str: ...
    def make_worktree(self, card_id: str) -> tuple[Path, str]: ...
    def commit(self, worktree: Path, paths: tuple[str, ...], message: str) -> str: ...
    def ready(self, card_id: str) -> None: ...
    def supersede(self, card_id: str, note: str) -> str: ...  # يلغي بطاقة لم تُلتقط بعد، ويعيد حالتها قبل ذلك كما في الدفتر


_DARK = re.compile(r"prefers-color-scheme:\s*dark|data-theme=[\"']dark[\"']")
_INK = re.compile(r"(\s*)--color-mark-ink\s*:\s*([^;]*);?")
# استعمال لا ذكر: اختبار «مسك» يسرد الاسم بين المتغيرات القديمة التي يجب غيابها (بطاقة v9 أبقته بسببه)
_USES_ACCENT = re.compile(r"var\(\s*--color-mark-accent\b")
STAMP = re.compile(rb'(<meta name="sima-build" content="[0-9a-f]+">)(?![^\n]*pragma: allowlist secret)')
UNIFY_ROOTS = (("frontend/src", (".css", ".vue", ".ts")), ("templates", (".html",)))  # حيث يُبدَّل لون العلامة القديم عند التوحيد
UNCLAIMED = ("created", "ready")  # بطاقة لم يلتقطها المشغّل: إعادة التسليم تلغيها ولا تمسّ ما بعدها
LEFT_SHOWN = 30  # أقصى ما تسرده البطاقة من مواضع بقي فيها اللون القديم أو ملفات حُذفت؛ الباقي بعدده


def patch_tokens_css(css: str, brand: str, accent: str | None, on_dark: str = "#ffffff") -> str:
    """يستبدل متغيرات الشعار القديمة (tile/ink/dot) بـ ink/accent ويعكس الحبر في كل كتلة داكنة. حتمي وidempotent.

    الكتلة داكنة إن حملت ترويستها أو ترويسة ما يحيط بها `prefers-color-scheme: dark` أو `data-theme="dark"`. حبر الشعار
    يُستبدل في موضعه في كل كتلة (التلقائية واليدوية)، وكتلة `:root` داكنة بلا حبر يُضاف إليها بعد ترويستها.
    accent فارغ: الرمز بلون واحد لا يستعمل لون تمييز، فلا يُعرَّف له `--color-mark-accent` ويُحذف القديم (كان يُكتب بلا شرط).
    ملف يعرّف ألوانه بـ`light-dark()` بلا كتل ليلية (رموز «مسك»): حبر الشعار يُكتب فيه بالصيغة نفسها في تعريف واحد."""
    brand, on_dark = brand.lower(), on_dark.lower()
    paired = "light-dark(" in css and not _DARK.search(css)
    light_ink = f"light-dark({brand}, {on_dark})" if paired else brand
    accent_line = f"--color-mark-accent: {accent.lower()};" if accent else ""
    comment = MARK_COMMENT_NEW if accent else MARK_COMMENT_MONO
    out: list[str] = []
    stack: list[list] = []  # الكتل المفتوحة: [سطر الترويسة، موضع ما بعدها في out، هل فيها حبر الشعار]
    root_done = False
    for line in css.split("\n"):
        s = line.strip()
        if re.match(r"--color-mark-(tile|dot|accent)\s*:", s):
            continue
        if MARK_COMMENT_OLD in line:
            out.append(line.replace(MARK_COMMENT_OLD, comment))
            continue
        m = _INK.match(line)
        if m:
            ind = m.group(1)
            if any(_DARK.search(b[0]) for b in stack):
                out.append(f"{ind}--color-mark-ink: {on_dark};")
            else:
                pair = roles_map.light_dark(m.group(2)) if paired else None
                keep = pair and roles_map.is_ref(pair[0])  # نهار يحيل إلى لون السمة (`var(--day-color)`): يبقى ويُكتب الليل وحده
                out.append(f"{ind}--color-mark-ink: " + (f"light-dark({pair[0]}, {on_dark})" if keep else light_ink) + ";")
                if accent_line:
                    out.append(ind + accent_line)
                root_done = True
            if stack:
                stack[-1][2] = True
            continue
        out.append(line)
        delta = line.count("{") - line.count("}")
        stack.extend([line, len(out), False] for _ in range(delta))
        for _ in range(-delta):
            if not stack:
                break
            head, pos, has_ink = stack.pop()
            if not has_ink and head.strip().startswith(":root") and (_DARK.search(head) or any(_DARK.search(b[0]) for b in stack)):
                ind = re.match(r"(\s*)", head).group(1) + "  "
                out.insert(pos, f"{ind}--color-mark-ink: {on_dark};")
    result = "\n".join(out)
    if not root_done:
        result += f"\n:root {{\n  /* {comment} */\n  --color-mark-ink: {light_ink};\n" + (f"  {accent_line}\n" if accent_line else "") + "}\n"
    return result


def patch_print_css(css: str, brand: str, accent: str | None) -> str:
    """الورق يثبّت ألوان الشعار على قيم الوضع النهاري: حبره لون العلامة وتمييزه لون التمييز. حتمي وidempotent.
    accent فارغ (رمز بلون واحد): سطر `--color-mark-accent` يُحذف كما حُذف من tokens.css."""
    css = re.sub(r"(--color-mark-ink\s*:\s*)[^;]+;", lambda m: f"{m.group(1)}{brand.lower()};", css)
    if accent:
        return re.sub(r"(--color-mark-accent\s*:\s*)[^;]+;", lambda m: f"{m.group(1)}{accent.lower()};", css)
    return re.sub(r"^[ \t]*--color-mark-accent\s*:[^;]+;[ \t]*\n|[ \t]*--color-mark-accent\s*:[^;]+;", "", css, flags=re.MULTILINE)


def _apply_paper(files: RepoFiles, writes: list[FileWrite], notes: list[str], paper: roles_map.PaperMap | None,
                 ident_ctx, version: int, print_css: str | None) -> None:
    """الورق يتبع الاتجاه المعتمد بخريطة الهدف: ملفات CSS (print.css من ناتج ترقيع الرمز) وثوابت بايثون. لا هوية كاملة في الحزمة
    أو ملف غائب يُذكر في البطاقة ولا يُكتب شيء."""
    if not paper or not (paper.css or paper.constants):
        return
    if not ident_ctx:
        notes.append("الورق: خريطة apply_paper لم تُطبَّق: لا هوية كاملة في الحزمة (identity/tokens/tokens.css) أو لا apply_identity.")
        return
    rules, roles = ident_ctx
    for path in paper.css:
        css = print_css if path == "frontend/src/styles/print.css" else files.read_text(path)
        if css is None:
            notes.append(f"{path}: غير موجود في المشروع فلم تُطبَّق عليه خريطة apply_paper.")
            continue
        res = roles_map.apply_paper_css(css, rules, roles, version, paper.skip)
        if res.css != css:
            writes[:] = [w for w in writes if w.path != path] + [FileWrite(path, res.css.encode("utf-8"))]
        notes.append(roles_map.paper_note(path, res.changes, res.literals, res.stray))
    for path, table in paper.constants:
        text = files.read_text(path)
        if text is None:
            notes.append(f"{path}: غير موجود في المشروع فلم تُطبَّق عليه خريطة apply_paper.")
            continue
        new, changes = roles_map.apply_constants(text, table, roles["light"])
        if new != text:
            writes.append(FileWrite(path, new.encode("utf-8")))
        notes.append(roles_map.paper_note(path, changes))


def _component(path: Path) -> bytes:
    """مكوّن الشعار كما في الحزمة عدا مقاس الأصل الثابت المكرَّر في وسمه (`export.drop_fixed_size`)."""
    return export.drop_fixed_size(path.read_text(encoding="utf-8")).encode("utf-8")


MARK_FILES = ("frontend/src/components/BrandMark.vue", "frontend/src/components/BrandLockup.vue",
              TOKENS_PATH, "frontend/src/styles/print.css")


def accent_in_use(package_dir: Path, files: RepoFiles, tokens_path: str = TOKENS_PATH) -> tuple[bool, list[str]]:
    """هل يلزم المشروعَ `--color-mark-accent`؟ (الرمز المعتمد يستعمله، ملفات أخرى في واجهة المشروع تستعمله). رمز بلون واحد
    كان يُعرَّف له لون تمييز بلا شرط والبطاقة تقول إنه يستعمله (الملاحظة 2 على تسليم «أوراق» v6)."""
    mark = any("--color-mark-accent" in (package_dir / n).read_text(encoding="utf-8")
               for n in ("BrandMark.vue", "BrandLockup.vue") if (package_dir / n).is_file())
    others = [] if mark else [rel for rel in files.walk("frontend/src")
                              if rel not in (*MARK_FILES, tokens_path) and Path(rel).suffix.lower() in (".vue", ".css", ".ts")
                              and _USES_ACCENT.search(files.read_text(rel) or "")]
    return mark, others


def light_brand(css: str) -> str:
    """لون العلامة النهاري في tokens.css المشروع (أول `--color-brand`)، أو فارغ إن لم يُعرَّف."""
    m = re.search(r"--color-brand\s*:\s*(#[0-9a-fA-F]{6})\b", css)
    return m.group(1).lower() if m else ""


def replace_color(text: str, old: str, new: str) -> str:
    """يستبدل لونًا بآخر في صيغتيه: الست عشرية بأي حالة، وثلاثية rgb بفواصلها كما هي."""
    out = re.sub(re.escape(old), new.lower(), text, flags=re.IGNORECASE)
    o, n = ([int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in (old, new))
    sep = r"(\s*,\s*|\s+)"
    return re.sub(rf"(rgba?\(\s*){o[0]}{sep}{o[1]}{sep}{o[2]}\b", lambda m: f"{m.group(1)}{n[0]}{m.group(2)}{n[1]}{m.group(3)}{n[2]}", out)


def _dark_lines(css: str) -> list[bool]:
    """لكل سطر في ملف CSS: هل هو داخل كتلة ليلية (ترويستها أو ترويسة ما يحيط بها تحمل الوضع الداكن)؟"""
    flags: list[bool] = []
    stack: list[bool] = []
    for line in css.split("\n"):
        flags.append(any(stack) or bool(_DARK.search(line)))
        delta = line.count("{") - line.count("}")
        stack.extend([bool(_DARK.search(line)) or any(stack)] * max(delta, 0))
        if delta < 0:
            del stack[max(len(stack) + delta, 0):]
    return flags


def replace_color_light(text: str, old: str, new: str, css: bool) -> str:
    """التوحيد للّون النهاري وحده: في ملف CSS لا تُمسّ أسطر الكتل الليلية ولو حملت القيمة القديمة (كان الاستبدال على الملف
    كله فلا يفرض «القيم الليلية لا تُمسّ» إلا مصادفةً، ت11)."""
    if not css:
        return replace_color(text, old, new)
    return "\n".join(line if dark else replace_color(line, old, new)
                     for line, dark in zip(text.split("\n"), _dark_lines(text), strict=True))


def old_color_lines(text: str, old: str, css: bool) -> list[int]:
    """أرقام الأسطر التي تحمل اللون بإحدى صيغه الثلاث: `#rrggbb`، والست عشرية بلا `#` (ثابت في بايثون أو OOXML)، وثلاثية rgb.
    أسطر الكتل الليلية في CSS خارج العدّ: هي ما لا يُمسّ بقصد."""
    bare = old.lstrip("#")
    o = [int(bare[i:i + 2], 16) for i in (0, 2, 4)]
    sep = r"(?:\s*,\s*|\s+)"
    pattern = re.compile(rf"(?<![0-9A-Fa-f]){bare}(?![0-9A-Fa-f])|rgba?\(\s*{o[0]}{sep}{o[1]}{sep}{o[2]}\b", re.IGNORECASE)
    dark = _dark_lines(text) if css else []
    return [i + 1 for i, line in enumerate(text.split("\n")) if pattern.search(line) and not (css and dark[i])]


def _allowlisted(html: bytes) -> bytes:
    """ختم الدليل `sima-build` بصمة ست عشرية يقرؤها detect-secrets سرًّا: يُفرد في سطره ويُعلَّم استثناءً في نسخة التسليم وحدها.

    الحزمة لا تُمسّ، فبصمة الدليل الذي اعتمده المالك كما هي."""
    return STAMP.sub(rb"\1 <!-- pragma: allowlist secret -->\n", html, count=1)


def patch_spa_html(html: str) -> str:
    """يضيف روابط manifest وapple-touch-icon وfavicon.ico بعد رابط favicon.svg إن لم تكن موجودة."""
    if 'rel="manifest"' in html:
        return html
    links = ('  <link rel="alternate icon" href="{% static \'favicon.ico\' %}">\n'
             '  <link rel="apple-touch-icon" href="{% static \'apple-touch-icon.png\' %}">\n'
             '  <link rel="manifest" href="{% static \'site.webmanifest\' %}">\n')
    m = re.search(r"^[ \t]*<link rel=\"icon\"[^\n]*\n", html, flags=re.MULTILINE)
    if not m:
        return html.replace("</head>", links + "</head>", 1)
    return html[: m.end()] + links + html[m.end():]


def manifest_with_prefix(manifest: str, static_prefix: str) -> str:
    data = json.loads(manifest)
    for icon in data.get("icons", []):
        src = str(icon.get("src", ""))
        if src.startswith("/") and not src.startswith(static_prefix):
            icon["src"] = static_prefix.rstrip("/") + src
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def identity_writes(package_dir: Path, slug: str) -> list[FileWrite]:
    """الهوية الكاملة المعتمدة (package/identity) إلى brand/<slug>/identity/ بلا ملفات JSON (تُقرأ بصماتها أسرارًا في فحص detect-secrets)."""
    root = package_dir / "identity"
    if not root.is_dir():
        return []
    return [FileWrite(f"{BRAND_DIR}/{slug}/identity/{p.relative_to(root).as_posix()}",
                      _allowlisted(p.read_bytes()) if p.suffix.lower() == ".html" else p.read_bytes())
            for p in sorted(root.rglob("*")) if p.is_file() and p.suffix.lower() != ".json"]


def plan_delivery(brief: Brief, package_dir: Path, repo: Path | RepoFiles, version: int, concept_id: str, static_prefix: str = "/static/",
                  palette: tuple[str, str] | None = None, unify_brand: bool = False,
                  apply_identity: Mapping | None = None, apply_paper: Mapping | None = None,
                  tokens_path: str = TOKENS_PATH, mirrors: Mapping[str, str] | None = None) -> DeliveryPlan:
    """خطة الكتابة: المكوّنان والأيقونات وmanifest وtokens وprint.css وspa.html ومجلد brand/ المرجعي، والهوية الكاملة إن اعتُمدت.

    palette: (brand, accent) المعتمدان فعلًا؛ في نطاق الهوية هما لونا الاتجاه المختار لا لونا الموجز الأصليان.
    unify_brand: قرار المالك لمشروع بعينه (deliver_targets.yaml): لون العلامة النهاري في التطبيق يصير لون الشعار المعتمد
    حيثما كُتب في واجهته وقوالبه واختباراتها؛ القيم الليلية لا تُمسّ.
    apply_identity: خريطة الهدف (deliver_targets.yaml) من متغيرات رموز التطبيق إلى أدوار الهوية المعتمدة (قرار المالك ق1):
    التطبيق يتبع الاتجاه كاملًا نهارًا وليلًا، والبطاقة تسرد كل قيمة تغيّرت وكل متغير لوني خارج الخريطة.
    apply_paper: خريطة الورق (deliver_targets.yaml): ملفات CSS تُطبَّق عليها خريطة apply_identity بقيم النهار وحدها، وثوابت ألوان
    في ملفات بايثون (مولّد Word) بأدوارها، فلا تبقى الورقة المطبوعة على اتجاه قديم بينما التطبيق على الجديد.
    tokens_path: ملف رموز التطبيق في هدفه (بند `tokens:`)؛ الافتراضي `frontend/src/styles/tokens.css`.
    mirrors: نسخ في المشروع تطابق ملفًا أو مجلدًا من الخطة بايتًا بايتًا (بند `mirrors:`)، كنسخ الواجهة التي تُبنى من frontend/ وحده
    («مسك» v10: كانت تبقى على الهوية السابقة فيسقط اختبار المطابقة)؛ مفتاح ينتهي بـ`/` مجلد يُحذف منه ما ليس في أصله."""
    slug = brief.project
    writes: list[FileWrite] = []
    notes: list[str] = []

    lockup = package_dir / "BrandLockup.vue"
    mark_vue = export.tidy_view_box(_component(package_dir / "BrandMark.vue").decode("utf-8"))
    writes.append(FileWrite("frontend/src/components/BrandMark.vue",
                            export.mark_header(mark_vue, brief, concept_id, lockup.is_file()).encode("utf-8")))
    favicon = (export.favicon_svg((package_dir / "favicon.svg").read_text(encoding="utf-8"), f"شعار {brief.name_ar}").encode("utf-8")
               if (package_dir / "favicon.svg").is_file() else None)
    files: RepoFiles = DirFiles(repo) if isinstance(repo, Path) else repo
    mark_accent, accent_users = accent_in_use(package_dir, files, tokens_path)
    notes.append("استبدال frontend/src/components/BrandMark.vue بالرمز المعتمد ("
                 + ("يستعمل --color-mark-ink و--color-mark-accent فقط)." if mark_accent else "بلون واحد: يستعمل --color-mark-ink وحده)."))
    if lockup.is_file():
        writes.append(FileWrite("frontend/src/components/BrandLockup.vue", _component(lockup)))
        notes.append("استبدال frontend/src/components/BrandLockup.vue بالقفل المعتمد (الرمز والكلمة مسارات؛ الخاصية height كما كانت).")
    for name in PUBLIC_FILES:
        p = package_dir / name
        if p.is_file():
            writes.append(FileWrite(f"frontend/public/{name}", favicon if name == "favicon.svg" and favicon else p.read_bytes()))
    writes.append(FileWrite("frontend/public/site.webmanifest",
                            manifest_with_prefix((package_dir / "site.webmanifest").read_text(encoding="utf-8"), static_prefix).encode("utf-8")))
    notes.append("أيقونات favicon.svg/ico وPNG وsite.webmanifest في frontend/public (مسارات الأيقونات تحت " + static_prefix + ").")

    brand, accent = palette or (brief.palette.brand, brief.palette.accent or brief.palette.brand)
    # رمز بلون واحد لا يُعرَّف له لون تمييز، إلا إن استعمل المتغيرَ ملفٌ آخر في واجهة المشروع (فيبقى معرَّفًا ويُذكر)
    mark_tone = accent if mark_accent or accent_users else None
    old_brand = ""
    identity_tokens = package_dir / "identity" / "tokens" / "tokens.css"
    ident_ctx = ((roles_map.parse_rules(apply_identity), roles_map.identity_roles(identity_tokens.read_text(encoding="utf-8"), slug))
                 if apply_identity and identity_tokens.is_file() else None)
    paper = roles_map.parse_paper(apply_paper) if apply_paper else None
    tokens = files.read_text(tokens_path)
    final_tokens: str | None = None
    if tokens is not None:
        if tokens_path != TOKENS_PATH:
            notes.append(f"رموز التطبيق في {tokens_path} (بند tokens لهذا الهدف في سِمة): ما يُذكر أدناه باسم tokens.css يعنيه.")
        old_brand = light_brand(tokens)
        patched = patch_tokens_css(tokens, brand, mark_tone)
        notes.append("tokens.css: حذف --color-mark-tile و--color-mark-dot، وتعريف --color-mark-ink (لون العلامة؛ أبيض في كل كتلة داكنة، "
                     "التلقائية واليدوية)" + (" و--color-mark-accent." if mark_accent else
                                              "؛ الرمز بلون واحد، و--color-mark-accent باقٍ لأن ملفات في المشروع تستعمله: "
                                              + "، ".join(accent_users) + "." if accent_users else
                                              "؛ الرمز بلون واحد فلا --color-mark-accent (حُذف إن وُجد)."))
        if apply_identity and ident_ctx:
            applied = roles_map.apply_roles(patched, ident_ctx[0], ident_ctx[1], version)
            patched = applied.css
            notes.append(roles_map.diff_note(applied, version))
        elif apply_identity:
            notes.append("tokens.css: خريطة apply_identity لم تُطبَّق: لا هوية كاملة في الحزمة (identity/tokens/tokens.css).")
        writes.append(FileWrite(tokens_path, patched.encode("utf-8")))
        final_tokens = patched
    printed =files.read_text("frontend/src/styles/print.css")
    if printed is not None:
        patched_print = patch_print_css(printed, brand, mark_tone)
        if patched_print != printed:
            writes.append(FileWrite("frontend/src/styles/print.css", patched_print.encode("utf-8")))
            notes.append("print.css: --color-mark-ink" + (" و--color-mark-accent على الورق بقيمتَي" if mark_tone else " على الورق بقيمة")
                         + " الوضع النهاري في tokens.css.")
        printed = patched_print
    _apply_paper(files, writes, notes, paper, ident_ctx, version, printed)

    spa = files.read_text("templates/spa.html")
    if spa is not None:
        writes.append(FileWrite("templates/spa.html", patch_spa_html(spa).encode("utf-8")))
        notes.append("templates/spa.html: روابط favicon.ico وapple-touch-icon وmanifest.")

    if unify_brand and old_brand and old_brand != brand.lower():
        touched = _unify_brand(files, writes, old_brand, brand.lower())
        if touched:
            notes.append(f"توحيد لون العلامة في التطبيق بقرار المالك: {old_brand} صار {brand.lower()} (لون الشعار) في: {'، '.join(touched)}. "
                         "القيم الليلية لم تُمسّ. حدّث ذكر اللون القديم في CLAUDE.md والوثائق إن وُجد.")
        left = _old_color_left(files, writes, old_brand, slug)
        if left:
            shown = "، ".join(left[:LEFT_SHOWN]) + (f"، و{len(left) - LEFT_SHOWN} موضعًا آخر" if len(left) > LEFT_SHOWN else "")
            notes.append(f"بقي لون العلامة القديم {old_brand} خارج ما وحّدته سِمة (بـ`#` أو بلا `#` أو ثلاثية rgb) في: {shown}. "
                         "سِمة لا تبدّل ثابتًا بلا `#` ولا ملفًا خارج الواجهة والقوالب: بدّله في مشروعك إن كان لون العلامة.")

    for p in sorted(package_dir.iterdir()):
        if p.suffix in (".svg", ".md", ".css"):  # لا JSON: سلاسل hash تُقرأ أسرارًا في فحص detect-secrets
            data = (favicon if p.name == "favicon.svg" and favicon else
                    export.tidy_view_box(p.read_text(encoding="utf-8")).encode("utf-8") if p.suffix == ".svg" else p.read_bytes())
            writes.append(FileWrite(f"{BRAND_DIR}/{slug}/{p.name}", data))
    notes.append(f"{BRAND_DIR}/{slug}/: الحزمة المرجعية (SVG ملوّن وأحادي ومعكوس، الكلمة والقفل، USAGE.md، tokens.css).")
    ident = identity_writes(package_dir, slug)
    if ident and ident_ctx:
        adopt = adoption.build(slug, version, concept_id, package_dir / "identity", ident_ctx[0], ident_ctx[1], final_tokens, files)
        ident.append(FileWrite(f"{BRAND_DIR}/{slug}/identity/{adoption.FILE_NAME}", adopt.yaml_text.encode("utf-8")))
        if adopt.motion_css:
            ident.append(FileWrite(f"{BRAND_DIR}/{slug}/identity/{adoption.MOTION_FILE}", adopt.motion_css.encode("utf-8")))
        notes.append(adopt.summary())
    if ident:
        writes.extend(ident)
        notes.append(f"{BRAND_DIR}/{slug}/identity/: الهوية الكاملة المعتمدة مرجعًا ({len(ident)} ملفًا): tokens بصيغها، والخطوط بترخيصها، "
                     "والأنماط والأيقونات والتطبيقات والشاشات والحركة، ودليل الهوية وعرض الكشف (HTML وPDF)، والمنصة الاستراتيجية.")
    mirror_dirs = _mirror(writes, mirrors or {}, notes)
    # ملفات هوية سابقة ليست في الهوية المعتمدة الآن تُحذف (كانت تبقى بجوار الجديدة فيُظن أنها منها، ت8)
    planned = {w.path for w in writes}
    stale = tuple(p for p in files.walk(f"{BRAND_DIR}/{slug}/identity") if p not in planned) if ident else ()
    stale += tuple(p for d in mirror_dirs for p in files.walk(d.rstrip("/")) if p not in planned)
    if stale:
        notes.append(f"{BRAND_DIR}/{slug}/identity/: حُذف ما ليس في الهوية المعتمدة الآن ({len(stale)} ملفًا من تسليم سابق): "
                     + "، ".join(p.removeprefix(f"{BRAND_DIR}/{slug}/identity/") for p in stale[:LEFT_SHOWN])
                     + (f"، و{len(stale) - LEFT_SHOWN} أخرى" if len(stale) > LEFT_SHOWN else "") + ".")
    return DeliveryPlan(project=slug, version=version, concept_id=concept_id, writes=tuple(writes), notes=tuple(notes), deletes=stale)


def _mirror(writes: list[FileWrite], mirrors: Mapping[str, str], notes: list[str]) -> list[str]:
    """يضيف نسخ بند mirrors من محتوى الخطة نفسه (بعد كل تحويل)، ويعيد مجلداته ليُحذف منها ما ليس في أصله."""
    planned = {w.path: w.content for w in writes}
    dirs: list[str] = []
    for dest, src in mirrors.items():
        dest, src = str(dest), str(src)
        if dest.endswith("/"):
            prefix = src.rstrip("/") + "/"
            items = {k.removeprefix(prefix): v for k, v in planned.items() if k.startswith(prefix)}
            if not items:
                raise RuntimeError(f"بند mirrors: لا ملفات في الخطة تحت {src} لنسخها إلى {dest}")
            writes.extend(FileWrite(dest + rel, data) for rel, data in sorted(items.items()))
            dirs.append(dest)
        elif src in planned:
            writes.append(FileWrite(dest, planned[src]))
        else:
            raise RuntimeError(f"بند mirrors: {src} ليس في الخطة فلا يُنسخ إلى {dest}")
        notes.append(f"{dest}: نسخة مطابقة لـ{src} (بند mirrors لهذا الهدف في سِمة).")
    return dirs


def _staged_text(writes: list[FileWrite], staged: dict[str, int], files: RepoFiles, rel: str) -> str | None:
    """نص الملف كما سيكون بعد الخطة: ما رقّعته إن كان فيها، وإلا ما في الشجرة؛ None لغير النصي."""
    if rel not in staged:
        return files.read_text(rel)
    try:
        return writes[staged[rel]].content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _unify_brand(files: RepoFiles, writes: list[FileWrite], old: str, new: str) -> list[str]:
    """يستبدل لون العلامة القديم بالجديد في ملفات الواجهة والقوالب النصية، فوق ما رقّعته الخطة؛ يعيد المسارات التي تغيّرت."""
    staged = {w.path: i for i, w in enumerate(writes)}
    touched: list[str] = []
    for sub, exts in UNIFY_ROOTS:
        for rel in files.walk(sub):
            suffix = Path(rel).suffix.lower()
            if suffix not in exts:
                continue
            text = _staged_text(writes, staged, files, rel)
            if text is None:
                continue
            fixed = replace_color_light(text, old, new, css=suffix == ".css")
            if fixed == text:
                continue
            if rel in staged:
                writes[staged[rel]] = FileWrite(rel, fixed.encode("utf-8"))
            else:
                staged[rel] = len(writes)
                writes.append(FileWrite(rel, fixed.encode("utf-8")))
            touched.append(rel)
    return touched


def _old_color_left(files: RepoFiles, writes: list[FileWrite], old: str, slug: str) -> list[str]:
    """مواضع بقي فيها اللون القديم بعد التوحيد، في الشجرة كلها عدا مرجع الهوية `brand/<slug>/` وملفات القفل: `مسار:سطر`.

    التوحيد يبدّل `#rrggbb` وثلاثية rgb في جذور الواجهة والقوالب وحدها؛ ثابت بلا `#` (مثل `BRAND = "842447"` في مولّد Word)
    أو ملف خارجها كان يبقى بلا ذكر فيصلحه المشروع بيده (ت3)."""
    staged = {w.path: i for i, w in enumerate(writes)}
    left: list[str] = []
    for rel in files.walk():
        if rel.startswith(f"{BRAND_DIR}/{slug}/") or rel.endswith((".lock", "-lock.json", "-lock.yaml")):
            continue
        text = _staged_text(writes, staged, files, rel)
        if text is not None:
            left.extend(f"{rel}:{n}" for n in old_color_lines(text, old, css=rel.endswith(".css")))
    return left


def apply_plan(plan: DeliveryPlan, root: Path) -> list[str]:
    """يكتب الخطة ويحذف ما أمرت بحذفه، ويعيد المسارات التي تغيّر محتواها فعلًا (الملف المطابق لا يُكتب ولا يُعدّ).

    المطابقة بلا اعتبار لنهايات الأسطر: نسخة العمل على ويندوز قد تكون CRLF والخطة LF، وgit لا يرى بينهما فرقًا."""
    def lf(data: bytes) -> bytes:
        return data.replace(b"\r\n", b"\n")

    changed: list[str] = []
    for w in plan.writes:
        p = root / w.path
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.is_file() and lf(p.read_bytes()) == lf(w.content):
            continue
        p.write_bytes(w.content)
        changed.append(w.path)
    for rel in plan.deletes:
        p = root / rel
        if p.is_file():
            p.unlink()
            changed.append(rel)
    return changed


def card_text(brief: Brief, plan: DeliveryPlan) -> tuple[str, str, str]:
    title = f"اعتماد هوية «{brief.wordmark_text}» من سِمة (المفهوم {plan.concept_id}، الإصدار v{plan.version})"
    body = ("الملفات مكتوبة ومودَعة في هذا الفرع بأداة سِمة؛ لا تعدّل الرمز أو ألوانه. ما تغيّر، ثم المطلوب التحقق منه:\n"
            + "\n".join(f"- {n}" for n in plan.notes)
            + "\n- شغّل اختبارات الواجهة (vitest: styles/designTokens.test.ts وstyles/contrast.test.ts) وأصلح أي متغير غير معرّف إن ظهر في مكوّنات أخرى.\n"
            "- تحقق أن الترويسة والوضع الداكن ولسان المتصفح تعرض الرمز الجديد بلا مربع مستدير.")
    success = "prepush_check.py يمرّ، واختبار designTokens يمرّ، وBrandMark.vue وfavicon.svg هما نسخة سِمة بلا تعديل."
    return title, body, success


def _record_applied(ws: Workspace, brief: Brief, marker: dict) -> dict:
    """يسجّل تسليمًا بلا بطاقة بنقطته المدموجة، مرة لكل إصدار: تسجيل سابق من النوع نفسه يبقى، ومن غيره يُرفض."""
    if not ws.done("package"):
        raise RuntimeError("لا حزمة معتمدة بعد؛ شغّل sima run أولًا.")
    if brief.identity.enabled and not ws.done("identity"):
        raise RuntimeError("الهوية الكاملة لم تُعتمد بعد؛ اعتمد دليل الهوية أولًا.")
    done = ws.read_marker("deliver")
    kind = "manual" if marker.get("manual") else "in_place"
    if done.get("card_id"):
        raise RuntimeError(f"سُلّم هذا الإصدار سابقًا في البطاقة {done.get('card_id', '')}؛ لا يُسجَّل تسليم بلا بطاقة فوقه.")
    if done and not done.get(kind):
        raise RuntimeError(f"سُجّل تسليم هذا الإصدار سابقًا بنوع آخر (النقطة {str(done.get('commit', ''))[:8]}).")
    if not done:
        ws.mark_done("deliver", marker)
    return ws.read_marker("deliver")


def deliver_in_place(ws: Workspace, brief: Brief, commit: str) -> dict:
    """مشروع الهوية هو مستودع سِمة نفسه: لا بطاقة ولا worktree؛ تُسجَّل نقطة git التي طبّقت الحزمة علامةَ تسليم، مرة لكل إصدار."""
    return _record_applied(ws, brief, {"in_place": True, "commit": commit})


def deliver_manual(ws: Workspace, brief: Brief, repo: Path, commit: str) -> dict:
    """تسليم يدوي بقرار المالك (مشروع بلا هدف في deliver_targets ولا مشغّل): جلسة المشروع طبّقت الحزمة بيدها ودمجتها،
    فتُسجَّل نقطة الدمج في مستودعها تسليمًا ودمجًا معًا، مرة لكل إصدار. لا تُكتب في المستودع شيء."""
    return _record_applied(ws, brief, {"manual": True, "repo": str(repo), "commit": commit})


def deliver(ws: Workspace, brief: Brief, target: DeliveryTarget, repo: Path, static_prefix: str = "/static/",
            unify_brand: bool = False, apply_identity: Mapping | None = None, apply_paper: Mapping | None = None,
            profile: str = "spa", styles: Sequence[str] = (), tokens_path: str = TOKENS_PATH,
            redeliver: bool = False, mirrors: Mapping[str, str] | None = None) -> DeliveryReceipt:
    """ينفّذ التسليم مرة واحدة لكل إصدار (علامة stages/deliver.json). changed في الإيصال ما تغيّر فعلًا لا كل ما في الخطة.

    redeliver (أمر المالك وحده، `sima deliver --redeliver`): الإصدار نفسه يُسلَّم ببطاقة جديدة من أساس الفرع الآن بعد أن تغيّر
    بند هدفه (خريطة ألوان أُضيفت بعد التسليم مثلًا). البطاقة السابقة تُلغى في دفترها إن لم تُلتقط بعد، وإلا تبقى وتُذكر حالتها
    في الجديدة؛ وتُحفظ في `previous` من علامة التسليم."""
    if not ws.done("package"):
        raise RuntimeError("لا حزمة معتمدة بعد؛ شغّل sima run أولًا.")
    done = ws.read_marker("deliver")
    if applied(done):
        where = "في مكانه" if done.get("in_place") else "يدويًّا"
        raise RuntimeError(f"سُلّم هذا الإصدار {where} (النقطة {str(done.get('commit', ''))[:8]})؛ لا بطاقة له.")
    if done and not redeliver:
        return DeliveryReceipt(card_id=done["card_id"], branch=done["branch"], worktree=done["worktree"], head=done["head"],
                               paths=tuple(done["paths"]), changed=tuple(done.get("changed", done["paths"])),
                               deleted=tuple(done.get("deleted", [])))
    if brief.identity.enabled and not ws.done("identity"):
        raise RuntimeError("الهوية الكاملة لم تُعتمد بعد؛ اعتمد دليل الهوية أولًا.")
    concept = json.loads((ws.package_dir / "concept.json").read_text(encoding="utf-8"))
    pal = ws.read_marker("package").get("palette") or []
    palette = (str(pal[2]), str(pal[3])) if len(pal) == 4 else None
    pending = ws.read_marker("deliver_pending")
    if done and pending.get("card_id") == done.get("card_id"):
        pending = {}  # معلّقة التسليم السابق المكتمل لا تُستأنف: إعادة التسليم بطاقة جديدة
    previous = [*done.get("previous", []), {k: done.get(k, "") for k in ("card_id", "branch", "head")}] if done else []
    plan_opts = (static_prefix, palette, unify_brand, apply_identity, apply_paper, tokens_path, mirrors)
    if pending.get("card_id"):
        card_id = str(pending["card_id"])  # محاولة سابقة أنشأت البطاقة ثم تعثّرت: تُستأنف هي لا تُنشأ أخرى
    else:
        # نص البطاقة من شجرة الأساس الذي يُفتح منه فرعها، لا من النسخة الرئيسة بفرعها وتعديلاتها غير المودَعة: كان يُحسب منها
        # والإيداع من شجرة البطاقة، فتصف البطاقة فرقًا غير الذي أُودع (ت7)
        base_plan = (plan_delivery_django(brief, ws.package_dir, target.base_files(), ws.version, str(concept["id"]), styles, apply_identity)
                     if profile == "django_static" else
                     plan_delivery(brief, ws.package_dir, target.base_files(), ws.version, str(concept["id"]), *plan_opts))
        title, body, success = (card_text_django if profile == "django_static" else card_text)(brief, base_plan)
        if done:
            old = str(done["card_id"])
            was = target.supersede(old, f"أعادت سِمة تسليم الإصدار v{ws.version} ببطاقة جديدة")
            body += (f"\n- تحلّ هذه البطاقة محلّ البطاقة {old} للإصدار نفسه (أُلغيت قبل التقاطها): تحمل ما فيها وما أُضيف بعدها."
                     if was in UNCLAIMED else
                     f"\n- سبقتها للإصدار نفسه البطاقة {old} (حالتها في الدفتر: {was or 'غير مقروءة'})؛ هذه من أساس الفرع الآن "
                     "وتحمل ما تغيّر بعدها.")
        card_id = target.new_card(title, body, success)
        ws.mark_done("deliver_pending", {"card_id": card_id, "repo": str(repo)})
    worktree, branch = target.make_worktree(card_id)
    # الترقيع من ملفات الـworktree نفسه (المأخوذ من origin/main) لا من النسخة الرئيسية بتعديلاتها غير المودعة أو فرعها الآخر
    plan = (plan_delivery_django(brief, ws.package_dir, DirFiles(Path(worktree)), ws.version, str(concept["id"]), styles, apply_identity)
            if profile == "django_static" else
            plan_delivery(brief, ws.package_dir, Path(worktree), ws.version, str(concept["id"]), *plan_opts))
    # محاولة تعثّرت بعد الكتابة لا تجد فرقًا في الثانية: ما تغيّر يُحفظ مع البطاقة المعلّقة ويُضم إليه
    changed = tuple(sorted({*pending.get("changed", []), *apply_plan(plan, worktree)}))
    deleted = tuple(sorted({*pending.get("deleted", []), *plan.deletes}))  # المحذوف في محاولة تعثّرت لا تراه الثانية في الشجرة
    ws.mark_done("deliver_pending", {"card_id": card_id, "repo": str(repo), "changed": list(changed), "deleted": list(deleted)})
    if profile == "django_static":
        what = "مرحلة الألوان على أنماط التطبيق"
    else:
        what = "الرمز والأيقونات والرموز اللونية والهوية الكاملة" if ws.done("identity") else "الرمز والأيقونات والرموز اللونية"
    head = target.commit(worktree, (*plan.paths, *deleted),
                         f"هوية «{brief.wordmark_text}» من سِمة: {what} (المفهوم {plan.concept_id}، v{plan.version})")
    target.ready(card_id)
    receipt = DeliveryReceipt(card_id=card_id, branch=branch, worktree=str(worktree), head=head, paths=plan.paths, changed=changed,
                              deleted=deleted)
    ws.mark_done("deliver", {"card_id": card_id, "branch": branch, "worktree": str(worktree), "head": head, "paths": list(plan.paths),
                             "changed": list(changed), "deleted": list(deleted), "repo": str(repo),
                             **({"previous": previous} if previous else {})})
    return receipt
