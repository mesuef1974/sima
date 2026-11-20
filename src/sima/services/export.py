"""تصدير الحزمة: SVG أساسي وأحادي ومعكوس وكلامي وقفل، favicon متعددة الدقات وwebmanifest، tokens.css،
BrandMark.vue، قواعد الاستعمال بالعربية. كل شيء في out/<project>/v<n>/package/."""
from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from ..domain import Brief, Concept, Package
from . import contrast, svgtools
from .audit import AuditReport
from .colorize import colorize
from .ports import Renderer
from .shaping import WordmarkSVG

ICO_SIZES = (16, 32, 48)
PNG_ICONS = {"favicon-32.png": 32, "apple-touch-icon.png": 180, "icon-192.png": 192, "icon-512.png": 512}


def build_ico(pngs: dict[int, bytes]) -> bytes:
    """ICO يحوي صور PNG (مدعوم منذ Vista): ترويسة + فهرس + البيانات."""
    sizes = sorted(pngs)
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    data = b""
    for s in sizes:
        blob = pngs[s]
        entries += struct.pack("<BBBBHHII", s if s < 256 else 0, s if s < 256 else 0, 0, 0, 1, 32, len(blob), offset)
        data += blob
        offset += len(blob)
    return head + entries + data


def webmanifest(brief: Brief, theme: str, background: str) -> str:
    return json.dumps({
        "name": brief.name_ar,
        "short_name": brief.wordmark_text,
        "lang": "ar",
        "dir": "rtl",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "theme_color": theme,
        "background_color": background,
        "display": "standalone",
    }, ensure_ascii=False, indent=2)


def mark_uses_accent(*svgs: str | None) -> bool:
    """هل في العلامة جزء تمييز (`data-tone="accent"`)؟ رمز بلون واحد لا يُعرَّف له لون تمييز ولا يُذكر له في الوثائق."""
    return any(s and 'data-tone="accent"' in s for s in svgs)


def tokens_css(brief: Brief, slug: str, mark_accent: bool = True) -> str:
    """مرجع ألوان العلامة في الحزمة. التعليق يطابق ما يكتبه التسليم في رموز المشروع (`deliver.MARK_COMMENT_NEW`): كان يقول
    «الشعار ثابت في الوضعين» والتسليم يعكس حبره في الوضع الداكن (ت9)."""
    p = brief.palette
    accent = p.accent or p.brand
    return (
        f"/* سِمة: رموز هوية {brief.name_ar} ({slug}): مرجع ألوان العلامة. التسليم يكتب متغيرات الشعار في tokens.css المشروع نفسه. */\n"
        ":root {\n"
        f"  --brand-paper: {p.paper};\n  --brand-ink: {p.ink};\n  --brand-primary: {p.brand};\n  --brand-accent: {accent};\n"
        "  /* الشعار: حبره لون العلامة على الفاتح و--color-mark-on-dark على الداكن"
        + ("، ولون التمييز ثابت" if mark_accent else "؛ الرمز بلون واحد فلا لون تمييز له") + " */\n"
        f"  --color-mark-ink: {p.brand};\n" + (f"  --color-mark-accent: {accent};\n" if mark_accent else "")
        + f"  --color-mark-paper: {p.paper};\n"
        f"  --color-mark-on-dark: #FFFFFF;\n"
        "}\n"
    )


def _css_var_svg(svg: str, brand: str, accent: str | None) -> str:
    """نسخة SVG بمتغيرات CSS بدل الألوان الصلبة، للاستعمال داخل مكوّن Vue."""
    return _vars(colorize(svg, brand, accent), {brand: "--color-mark-ink", **({accent: "--color-mark-accent"} if accent and accent != brand else {})})


def _vars(svg: str, names: dict[str, str]) -> str:
    """يستبدل كل لون صلب في fill وstroke بمتغيّره، واللون نفسه قيمة احتياطية."""
    for color, var in names.items():
        for attr in ("fill", "stroke"):
            svg = svg.replace(f'{attr}="{color}"', f'{attr}="var({var}, {color})"')
    return svg


def drop_fixed_size(svg: str) -> str:
    """يحذف مقاس الأصل الثابت من وسم svg الأول: المكوّن يحمل مقاسه خاصيةً (`:width`)، وسمة مكرّرة في الوسم يردّها eslint
    المشروع («مسك» v5). يُطبَّق عند التوليد وعند التسليم، فحزمة معتمدة بُنيت قبله تُسلَّم سليمة دون إعادة بنائها."""
    fixed = re.compile(r'\s(?:width|height)="[^"]*"')
    return re.sub(r"<svg\b[^>]*>", lambda m: fixed.sub("", m.group(0)), svg, count=1)


NIGHT_FAVICON = "@media (prefers-color-scheme: dark) { path { fill: #ffffff; } }"
_SHAPES = re.compile(r"<(?:circle|ellipse|rect|polygon|polyline)\b")


def tidy_view_box(svg: str) -> str:
    """أرقام viewBox الأول بلا أصفار زائدة (`100.00000` ← `100`): اختبار المشروع يقرأ النسبة منه («مسك» v10)."""
    def tidy(m: re.Match) -> str:
        nums = [n for n in re.split(r"[\s,]+", m.group(1).strip()) if n]
        try:
            return 'viewBox="' + " ".join(f"{float(n):g}" for n in nums) + '"'
        except ValueError:
            return m.group(0)
    return re.sub(r'viewBox="([^"]*)"', tidy, svg, count=1)


def favicon_svg(svg: str, title: str) -> str:
    """أيقونة المتصفح: عنوانها اسم العلامة لا اسم المسودة، وتبيضّ على شريط تبويب داكن كحبر العلامة ليلًا (ط4 «مسك» v10).
    يُطبَّق عند التوليد وعند التسليم، فحزمة معتمدة بُنيت قبله تُسلَّم سليمة دون إعادة بنائها؛ وتطبيقه مرتين كمرة."""
    svg = tidy_view_box(re.sub(r"<svg\b([^>]*?)\s*/>", r"<svg\1></svg>", svg, count=1))
    svg = re.sub(r"<title>.*?</title>", "", svg, flags=re.DOTALL)
    head = f"<title>{title}</title>"
    if "prefers-color-scheme: dark" not in svg:
        rules = NIGHT_FAVICON
        if _SHAPES.search(svg):
            rules += " @media (prefers-color-scheme: dark) { circle, ellipse, rect, polygon, polyline { fill: #ffffff; } }"
        if 'fill="none"' in svg or "stroke=" in svg:  # ما رُسم خطًّا يبيضّ خطُّه ولا يُملأ
            rules += (' @media (prefers-color-scheme: dark) { [fill="none"] { fill: none; }'
                      ' [stroke]:not([stroke="none"]) { stroke: #ffffff; } }')
        head += f"<style>{rules}</style>"
    return re.sub(r"(<svg\b[^>]*>)", lambda m: m.group(1) + head, svg, count=1)


def mark_header(vue: str, brief: Brief, concept_id: str, lockup: bool) -> str:
    """تعليق رأس BrandMark.vue: يصف الرمز وحده لا جملة الشعار الكامل (ط5 «مسك» v10: التعليق وصف DESIGN والاسم والرمز مسار وحده)."""
    what = "الرمز وحده بلا الكلمة، والشعار الكامل بالكلمة في BrandLockup.vue" if lockup else "الرمز"
    text = (f"// رمز {brief.name_ar}: {what}. مسارات بلا نص حي بحبر --color-mark-ink (لون العلامة نهارًا وأبيض ليلًا).\n"
            f"// مُولَّد بأداة سِمة (المفهوم {concept_id})؛ المسار نفسه في public/favicon.svg وbrand/{brief.project}/favicon.svg."
            " لا يُعدَّل هنا.\n")
    return re.sub(r'(<script setup lang="ts">\n)(?://[^\n]*\n)*', lambda m: m.group(1) + text, vue, count=1)


def _vue_svg(svg: str, opening: str) -> str:
    """SVG داخل قالب Vue: بلا إعلان XML ولا عنوان ولا سمات بيانات، وبوسم افتتاح المكوّن."""
    svg = re.sub(r"<\?xml[^>]*\?>", "", svg)
    svg = re.sub(r"<title>.*?</title>", "", svg, flags=re.DOTALL)
    svg = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    svg = drop_fixed_size(svg)
    svg = re.sub(r"<svg\s*", opening, svg, count=1)
    svg = re.sub(r'\srole="img"', "", svg)
    return re.sub(r'\sdata-(tone|role)="[^"]*"', "", svg)


def brand_lockup_vue(lockup_svg: str, brief: Brief) -> str:
    """مكوّن القفل: الرمز بحبر الشعار (يتبع السمة) والكلمة بحبر النص، مسارات بلا نص حي؛ ارتفاعه خاصية وعرضه يتبعه."""
    p = brief.palette
    accent = p.accent if p.accent and p.accent != p.brand else None
    inner = _wordmark_ink(colorize(lockup_svg, p.brand, p.accent), p.brand, p.ink)
    inner = _vars(inner, {p.brand: "--color-mark-ink", **({accent: "--color-mark-accent"} if accent else {}),
                          **({p.ink: "--color-ink"} if p.ink != p.brand else {})})
    inner = _vue_svg(inner, '<svg class="brand-lockup" :height="height" aria-hidden="true" focusable="false" ')
    return (
        "<script setup lang=\"ts\">\n"
        f"// قفل {brief.name_ar}: الرمز والكلمة «{brief.wordmark_text}» مسارات بلا نص حي. حبر الرمز يتبع السمة والكلمة بحبر النص.\n"
        f"// مُولَّد بأداة سِمة؛ النسخة نفسها في brand/{brief.project}/{brief.project}-lockup.svg. لا يُعدَّل هنا.\n"
        "withDefaults(defineProps<{ height?: number }>(), { height: 40 });\n"
        "</script>\n\n<template>\n  " + inner + "\n</template>\n\n"
        "<style scoped>\n.brand-lockup {\n  flex: none;\n  display: block;\n  inline-size: auto;\n}\n</style>\n"
    )


def brand_mark_vue(svg: str, brief: Brief, concept: Concept, lockup: bool = False) -> str:
    p = brief.palette
    inner = _vue_svg(tidy_view_box(_css_var_svg(svg, p.brand, p.accent)),
                     '<svg class="brand-mark" :width="size" :height="size" aria-hidden="true" focusable="false" ')
    return mark_header(
        "<script setup lang=\"ts\">\n"
        "withDefaults(defineProps<{ size?: number }>(), { size: 36 });\n"
        "</script>\n\n<template>\n  " + inner + "\n</template>\n\n"
        "<style scoped>\n.brand-mark {\n  flex: none;\n  display: block;\n}\n</style>\n",
        brief, concept.id, lockup)


def usage_md(brief: Brief, concept: Concept, slug: str, files: list[str], audit: AuditReport | None, min_mark_px: int = 16,
             mark_accent: bool = True, min_stroke_px: float | None = None, min_wordmark_px: int | None = None) -> str:
    p = brief.palette
    accent = p.accent or p.brand
    c_brand = contrast.contrast_ratio(p.brand, p.paper)
    c_ink = contrast.contrast_ratio(p.ink, p.paper)
    c_white = contrast.contrast_ratio("#FFFFFF", p.brand)
    c_acc = contrast.contrast_ratio(accent, p.paper)
    lines = [
        f"# قواعد استعمال علامة «{brief.name_ar}»", "",
        f"المفهوم المعتمد: {concept.id} «{concept.name}». الفكرة بجملة: {concept.sentence}", "",
        "## الصيغ",
        f"- `{slug}-mark.svg` الرمز بالألوان: للترويسة والواجهة على الورق الفاتح.",
        f"- `{slug}-mark-mono.svg` أحادي أسود: للطباعة بلون واحد والختم.",
        f"- `{slug}-mark-reversed.svg` أبيض على داكن: للوضع الداكن والخلفيات الداكنة.",
        f"- `{slug}-wordmark.svg` الكلمة «{brief.wordmark_text}» مسارات بلا نص حي.",
        f"- `{slug}-lockup.svg` الرمز والكلمة معًا (الرمز على اليمين في RTL).",
        "- `favicon.svg`، `favicon.ico` (16/32/48)، `favicon-32.png`، `apple-touch-icon.png`، `icon-192.png`، `icon-512.png`، `maskable-512.png`، `site.webmanifest`.",
        "- `tokens.css` متغيرات الألوان، `BrandMark.vue` مكوّن Vue 3 للرمز، و`BrandLockup.vue` للقفل (إن وُجد قفل).",
        "- أين تجدها: كلها في حزمة سِمة (`package/` من الإصدار). في مشروع استلم بأمر التسليم: ملفات SVG وهذا الملف و`tokens.css`"
        f" بجواره في `brand/{slug}/`، والأيقونات و`site.webmanifest` في `frontend/public/`، والمكوّنان في `frontend/src/components/`.", "",
        "## المساحة الخالية والحد الأدنى",
        "- اترك حول الرمز مساحة لا تقل عن ربع عرضه من كل جهة.",
        f"- الحد الأدنى للرمز وحده {min_mark_px} بكسل على الشاشة و6 مم في الطباعة؛ للقفل مع الكلمة"
        f" {min_mark_px if min_mark_px > 96 else 24} بكسل ارتفاعًا.",
        *([f"- الشعار الكامل (`{slug}-wordmark.svg` والقفل) لا يقل عرضه عن {min_wordmark_px} بكسل على الشاشة؛ دونه يُستعمل الرمز وحده."
           " حدّ يعلنه المالك."] if min_wordmark_px else []),
        *(["- ملفات favicon دون هذا الحد (16 بكسل) مولّدة للتوافق فقط: حدّ السماكة لا يتحقق فيها، بعلم المالك عند الاعتماد."]
          if 16 < min_mark_px <= 96 else []),
        *(["- الأيقونات دون هذا الحد (favicon وapple-touch-icon وما صغر عنه) مولّدة للتوافق فقط: حدّ السماكة لا يتحقق فيها،"
           " بعلم المالك عند الاعتماد."] if min_mark_px > 96 else []),
        "- لا تدوير، لا تمديد، لا ظل، لا تدرج، لا حدود مضافة، لا تغيير نسب الرمز إلى الكلمة.", "",
        "## الألوان",
        f"| الدور | القيمة | التباين على الورق {p.paper} |", "|---|---|---|",
        f"| لون العلامة | {p.brand} | {c_brand}:1 |",
        f"| الحبر | {p.ink} | {c_ink}:1 |",
        (f"| التمييز | {accent} | {c_acc}:1 |" if mark_accent else
         f"| لون التمييز في الهوية (الرمز بلون واحد لا يستعمله) | {accent} | {c_acc}:1 |"),
        f"| نص أبيض على لون العلامة | #FFFFFF | {c_white}:1 |", "",
        "## إعلان العناصر الزخرفية والمعلوماتية (WCAG 1.4.11)",
        "- الرمز كاملًا عنصر معلوماتي: يجب أن يبقى تباينه مع خلفيته 3:1 على الأقل (محقَّق أعلاه).",
        *(["- عناصر التمييز (data-tone=\"accent\") زخرفية: العلامة تُعرف بدونها، فهي معفاة من شرط التباين."] if mark_accent else []), "",
        "## الربط في المشروع",
        "مشروع استلم الحزمة بأمر التسليم (`sima deliver`) ربطُه منجز في فرع بطاقته ولا خطوة يدوية فيه: المكوّنان والأيقونات وروابط"
        " `<head>` في القالب، ومتغيرات الشعار (`--color-mark-*`) مكتوبة في `tokens.css` المشروع نفسه، حبرها لون العلامة على الفاتح"
        " وأبيض على الداكن. الخطوات الآتية لمشروع يربط بيده فقط:",
        "1. انسخ `favicon.svg` و`favicon.ico` وملفات PNG و`site.webmanifest` إلى `public/`.",
        "2. عرّف `--color-mark-ink`" + (" و`--color-mark-accent`" if mark_accent else "") + " في رموز مشروعك بقيم `tokens.css` هذه،"
        " واجعل `--color-mark-ink` أبيض في الوضع الداكن.",
        "3. استبدل `components/BrandMark.vue` و`components/BrandLockup.vue` بالمولَّدَين (لا تعدّل الملفات القديمة في مكانها: هذا إصدار جديد).",
        "4. في `<head>`: `<link rel=\"icon\" href=\"/favicon.svg\" type=\"image/svg+xml\">`، و`<link rel=\"icon\" href=\"/favicon.ico\" sizes=\"any\">`، و`<link rel=\"apple-touch-icon\" href=\"/apple-touch-icon.png\">`، و`<link rel=\"manifest\" href=\"/site.webmanifest\">`.", "",
        "## الفحص الآلي عند الاعتماد",
    ]
    if audit:
        m = audit.metrics
        floor = f"{min_stroke_px:g} يعلنه المالك بدل 1.5، قراره 2026-11-15" if min_stroke_px is not None else "1.5"
        lines += [f"- أصغر سماكة عند {m.get('base_size', 16)} بكسل: {m.get('min_stroke_px')} (الحد {floor}).",
                  f"- تغطية صغير/256: {m.get('coverage_ratio')}؛ مكوّنات عند الحجم الصغير: {m.get('components_small')}.",
                  f"- نقاط الارتكاز: {m.get('anchors')}؛ الأشكال: {m.get('shapes')}."]
        sim = m.get("similarity") or []
        if sim:
            lines.append("- أقرب مراجع إدراكيًا (للعلم؛ ليست تصريحًا قانونيًا): " + "، ".join(f"{s['brand']} ({s['distance']}/64)" for s in sim[:3]))
        lines.append("- فحص العلامة التجارية رسميًا (وزارة التجارة والصناعة/WIPO) مسؤولية المالك قبل أي نشر تجاري.")
    lines += ["", "## ملفات الحزمة", "ما في `package/` من إصدار سِمة؛ المنسوخ منها إلى المشروع ومواضعه في قسم «الصيغ» أعلاه.",
              *[f"- {f}" for f in files], ""]
    return "\n".join(lines)


@dataclass
class ExportInputs:
    brief: Brief
    concept: Concept
    svg: str  # أبيض/أسود أساسي
    wordmark: WordmarkSVG | None
    lockup_svg: str | None
    audit: AuditReport | None
    preview_html: str | None
    min_mark_px: int = 16  # أصغر حجم يجتاز فيه الرمز حدّ السماكة (علامة اعتُمدت خارج الخط قد تعلن حدًّا أعلى)
    brief_hash: str = ""  # بصمة موجز التشغيل (`run.json`): موجز الحزمة تُبدَّل ألوانه بالاتجاه فبصمته لا تطابق تشغيلًا (ت10)
    run_key: str = ""
    min_stroke_px: float | None = None  # حدّ سماكة أدنى أعلنه المالك يغلب 1.5 (قراره 2026-11-15)؛ None = الافتراضي
    min_wordmark_px: int | None = None  # أصغر عرض للشعار الكامل يعلنه المالك (قراره 2026-11-20)؛ None = بلا سطر

    def fingerprint(self, version: int) -> str:
        """بصمة كل ما يدخل ملفات الحزمة: مخبؤها كان الألوان وحدها، فتغيّر خط الكلمة أو اسم العلامة يعيد حزمة قديمة (ت4).
        الفحص مشتق من الرمز والمعاينة نسخة للاطلاع، فلا يدخلان."""
        b, c = self.brief, self.concept
        data = {"palette": [b.palette.paper, b.palette.ink, b.palette.brand, b.palette.accent], "project": b.project,
                "name_ar": b.name_ar, "wordmark_text": b.wordmark_text,
                "concept": [c.id, c.name, c.family.value, c.medium.value, c.sentence, c.construction, c.reference],
                "svg": self.svg, "wordmark": self.wordmark.svg if self.wordmark else None, "lockup": self.lockup_svg,
                "min_mark_px": self.min_mark_px, "brief_hash": self.brief_hash, "run_key": self.run_key, "version": version}
        if self.min_stroke_px is not None:  # بلا إعلان تبقى البصمة كما كانت
            data["min_stroke_px"] = self.min_stroke_px
        if self.min_wordmark_px is not None:
            data["min_wordmark_px"] = self.min_wordmark_px
        return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


class ExportService:
    def __init__(self, renderer: Renderer):
        self._r = renderer

    def export(self, inp: ExportInputs, root: Path, version: int) -> Package:
        b, c = inp.brief, inp.concept
        slug = b.project
        root.mkdir(parents=True, exist_ok=True)
        files: list[str] = []

        def put(name: str, content: str | bytes) -> None:
            p = root / name
            if isinstance(content, str):
                p.write_text(content, encoding="utf-8")
            else:
                p.write_bytes(content)
            files.append(name)

        title = f"شعار {b.name_ar}"
        # عنوان الرمز اسم العلامة: عنوان المصدر اسم مسودته (`knot-gap3` في «مسك» v10)
        base = svgtools.ensure_title(re.sub(r"<title>.*?</title>", "", svgtools.strip_background(inp.svg), flags=re.DOTALL), title)
        color = colorize(base, b.palette.brand, b.palette.accent)
        put(f"{slug}-mark.svg", color)
        put(f"{slug}-mark-mono.svg", svgtools.mono(base))
        put(f"{slug}-mark-reversed.svg", svgtools.reversed_(base, ink="#FFFFFF", background=b.palette.ink))
        put(f"{slug}-mark-white.svg", svgtools.mono(base, "#FFFFFF"))
        if inp.wordmark:
            put(f"{slug}-wordmark.svg", svgtools.recolor(inp.wordmark.svg, {"#000000": b.palette.ink}))
        if inp.lockup_svg:
            lock_color = colorize(inp.lockup_svg, b.palette.brand, b.palette.accent)
            lock_color = _wordmark_ink(lock_color, b.palette.brand, b.palette.ink)
            put(f"{slug}-lockup.svg", lock_color)
            put(f"{slug}-lockup-mono.svg", svgtools.mono(inp.lockup_svg))
            put("BrandLockup.vue", brand_lockup_vue(inp.lockup_svg, b))
        put("favicon.svg", favicon_svg(color, title))  # الأيقونات النقطية من الملوّن: المتصفح بلا خلفية قد يبيّضها
        pngs = {s: self._r.render_png(color, s, None) for s in ICO_SIZES}
        put("favicon.ico", build_ico(pngs))
        for name, size in PNG_ICONS.items():
            bg = b.palette.paper if name == "apple-touch-icon.png" else None
            put(name, self._r.render_png(color, size, bg))
        maskable = svgtools.with_background(_padded(color, 0.2), b.palette.brand)
        maskable = svgtools.recolor(maskable, {svgtools.normalize_hex(b.palette.brand): "#FFFFFF"}, keep_background=True)
        put("maskable-512.png", self._r.render_png(maskable, 512, None))
        put("site.webmanifest", webmanifest(b, b.palette.brand, b.palette.paper))
        mark_accent = mark_uses_accent(base, inp.lockup_svg)
        put("tokens.css", tokens_css(b, slug, mark_accent))
        put("BrandMark.vue", brand_mark_vue(base, b, c, lockup=bool(inp.lockup_svg)))
        if inp.audit:
            put("audit.json", json.dumps(inp.audit.to_dict(), ensure_ascii=False, indent=2))
        if inp.preview_html:
            put("preview.html", inp.preview_html)
        put("concept.json", json.dumps({
            "id": c.id, "name": c.name, "family": c.family.value, "medium": c.medium.value, "sentence": c.sentence,
            "construction": c.construction, "reference": c.reference, "version": version, "brief_hash": inp.brief_hash or b.hash(),
            **({"run_key": inp.run_key} if inp.run_key else {}),
        }, ensure_ascii=False, indent=2))
        put("USAGE.md", usage_md(b, c, slug, [*sorted(files), "USAGE.md"], inp.audit, inp.min_mark_px, mark_accent, inp.min_stroke_px,
                                     inp.min_wordmark_px))
        return Package(project=b.project, version=version, concept_id=c.id, root=root, files=tuple(sorted(files)))


def _wordmark_ink(lockup_svg: str, brand: str, ink: str) -> str:
    """في القفل الملوّن تبقى الكلمة بلون الحبر لا لون العلامة."""
    root = svgtools.parse(lockup_svg)
    for el in root.iter():
        if el.get("id") == "wordmark":
            for sub in el.iter():
                for attr in ("fill", "stroke"):  # كلمة مرسومة بخط (stroke) تُلوَّن كالمملوءة
                    if sub.get(attr) and sub.get(attr) != "none":
                        sub.set(attr, ink)
    return svgtools.to_string(root)


def _padded(svg: str, ratio: float) -> str:
    """يوسّع viewBox بهامش نسبي (للأيقونة القابلة للقصّ maskable)."""
    root = svgtools.parse(svg)
    vb = svgtools.view_box(root) or (0.0, 0.0, 256.0, 256.0)
    x, y, w, h = vb
    px, py = w * ratio, h * ratio
    root.set("viewBox", f"{x - px:g} {y - py:g} {w + 2 * px:g} {h + 2 * py:g}")
    return svgtools.to_string(root)
