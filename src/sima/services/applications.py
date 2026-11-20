"""تطبيقات الهوية: قوالب حتمية تُغذّى بالاتجاه المعتمد (الأدوار والخطوط والنمط) والعلامة والمنصة الاستراتيجية.

كل تطبيق SVG مستقل بنص مشكَّل إلى مسارات؛ وتوقيع البريد HTML بأنماط مضمّنة لأن عملاء البريد لا يقرؤون SVG.
النصوص التي ليست من المنصة الاستراتيجية أمثلة مكانية واضحة («الاسم الكامل») يستبدلها المستعمل.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from xml.sax.saxutils import escape

from .compose import Font, Typesetter, embed, pattern_def, svg_doc


@dataclass(frozen=True)
class AppKit:
    name_ar: str
    tagline: str
    headline: str
    points: tuple[str, ...]
    roles: dict[str, str]
    heading: Font
    body: Font
    numerals: str
    mark: str
    mark_white: str
    mark_mono: str
    lockup: str
    lockup_white: str
    lockup_mono: str
    motif_soft: str    # على الورق
    motif_strong: str  # على لون العلامة
    radius: int = 4

    def digit(self, n: int) -> str:
        s = str(n)
        return s.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")) if self.numerals == "arab" else s


@dataclass(frozen=True)
class App:
    id: str
    title: str
    width: int
    height: int
    svg: str


def print_header(k: AppKit, t: Typesetter) -> App:
    W, H = 2480, 472
    body = [f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>', embed(k.lockup_mono, W - 120 - 900, 70, 900, 250, "xMaxYMid")]
    for i, label in enumerate(("الاسم:", "الصف:", "التاريخ:")):
        y = 150 + i * 100
        body.append(t.line(label, k.body, 46, 1380, y, "#000000"))
        lw = t.width(label, k.body, 46)
        body.append(f'<rect x="120" y="{y + 8}" width="{1380 - lw - 30 - 120:.0f}" height="4" fill="#000000"/>')
    body.append(f'<rect x="120" y="{H - 52}" width="{W - 240}" height="8" fill="#000000"/>')
    return App("print-header", "ترويسة الورقة المطبوعة (أبيض وأسود)", W, H, svg_doc(W, H, "".join(body), "ترويسة الورقة المطبوعة"))


def letterhead(k: AppKit, t: Typesetter) -> App:
    W, H, m = 2480, 3508, 180
    r = k.roles
    body = [f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>', embed(k.lockup, W - m - 1100, 150, 1100, 300, "xMaxYMid"),
            f'<rect x="{m}" y="520" width="{W - 2 * m}" height="6" fill="{r["brand"]}"/>',
            f'<rect x="0" y="{H - 260}" width="{W}" height="260" fill="url(#m)"/>',
            t.line(k.tagline, k.body, 44, W - m, H - 330, r["text_muted"]),
            t.line("العنوان · الهاتف · البريد الإلكتروني", k.body, 40, m, H - 330, r["text_muted"], anchor="start")]
    return App("letterhead", "الورقة الرسمية A4", W, H, svg_doc(W, H, "".join(body), "الورقة الرسمية", pattern_def("m", k.motif_soft, 260)))


def social_avatar(k: AppKit, t: Typesetter) -> App:
    W = 1080
    body = f'<rect width="{W}" height="{W}" fill="{k.roles["brand"]}"/>' + embed(k.mark_white, 240, 240, 600, 600)
    return App("social-avatar", "صورة الحساب", W, W, svg_doc(W, W, body, "صورة الحساب"))


def social_cover(k: AppKit, t: Typesetter) -> App:
    W, H = 1500, 500
    r = k.roles
    body = [f'<rect width="{W}" height="{H}" fill="{r["bg"]}"/>', f'<rect width="600" height="{H}" fill="url(#m)"/>',
            embed(k.lockup, 700, 110, 720, 180, "xMaxYMid"), t.line(k.tagline, k.heading, 46, 1420, 390, r["text"])]
    return App("social-cover", "غلاف الحساب", W, H, svg_doc(W, H, "".join(body), "غلاف الحساب", pattern_def("m", k.motif_soft, 150)))


def social_post(k: AppKit, t: Typesetter) -> App:
    W = 1080
    r = k.roles
    text, bottom = t.block(k.headline, k.heading, 84, 1000, 300, 900, r["on_brand"], 1.35, max_lines=4)
    body = [f'<rect width="{W}" height="{W}" fill="{r["brand"]}"/>', embed(k.mark_white, 860, 80, 140, 140, "xMaxYMin"), text,
            t.line(k.name_ar, k.body, 36, 1000, min(bottom + 90, 820), r["on_brand"]),
            f'<rect x="0" y="880" width="{W}" height="200" fill="url(#m)"/>']
    return App("social-post", "منشور", W, W, svg_doc(W, W, "".join(body), "منشور", pattern_def("m", k.motif_strong, 200)))


def slide_title(k: AppKit, t: Typesetter) -> App:
    W, H = 1920, 1080
    r = k.roles
    text, bottom = t.block(k.name_ar, k.heading, 110, 1800, 330, 1100, r["text"], 1.25, max_lines=2)
    body = [f'<rect width="{W}" height="{H}" fill="{r["bg"]}"/>', f'<rect width="560" height="{H}" fill="url(#m)"/>', text,
            f'<rect x="1560" y="{bottom + 40:.0f}" width="240" height="10" fill="{r["accent"]}"/>',
            t.line(k.tagline, k.body, 48, 1800, bottom + 150, r["text_muted"]),
            embed(k.lockup, 1800 - 420, 900, 420, 110, "xMaxYMid")]
    return App("slide-title", "شريحة العنوان", W, H, svg_doc(W, H, "".join(body), "شريحة العنوان", pattern_def("m", k.motif_soft, 220)))


def slide_content(k: AppKit, t: Typesetter) -> App:
    W, H = 1920, 1080
    r = k.roles
    body = [f'<rect width="{W}" height="{H}" fill="{r["bg"]}"/>', t.line("عنوان الشريحة", k.heading, 72, 1800, 200, r["text"]),
            f'<rect x="{1800 - 160}" y="240" width="160" height="8" fill="{r["brand"]}"/>']
    y = 340
    for p in k.points[:3]:
        body.append(f'<rect x="{1800 - 18}" y="{y + 14}" width="18" height="18" fill="{r["brand"]}"/>')
        text, bottom = t.block(p, k.body, 44, 1800 - 50, y, 1400, r["text"], 1.6, max_lines=2)
        body.append(text)
        y = bottom + 70
    body += [embed(k.mark, 120, 960, 60, 60, "xMinYMid"), t.line(k.digit(3), k.body, 32, 1800, 1010, r["text_muted"])]
    return App("slide-content", "شريحة المحتوى", W, H, svg_doc(W, H, "".join(body), "شريحة المحتوى"))


def card_front(k: AppKit, t: Typesetter) -> App:
    W, H = 1050, 600
    body = f'<rect width="{W}" height="{H}" fill="{k.roles["brand"]}"/>' + embed(k.lockup_white, 175, 200, 700, 200)
    return App("card-front", "بطاقة العمل: الوجه", W, H, svg_doc(W, H, body, "بطاقة العمل، الوجه"))


def card_back(k: AppKit, t: Typesetter) -> App:
    W, H = 1050, 600
    r = k.roles
    body = [f'<rect width="{W}" height="{H}" fill="{r["bg"]}"/>', t.line("الاسم الكامل", k.heading, 52, 960, 190, r["text"]),
            t.line("المسمّى الوظيفي", k.body, 32, 960, 245, r["text_muted"])]
    for i, line in enumerate(("البريد الإلكتروني", "رقم الهاتف", "الموقع الإلكتروني")):
        body.append(t.line(line, k.body, 28, 960, 350 + i * 50, r["text"]))
    body += [embed(k.mark, 90, 90, 200, 200, "xMinYMin"), f'<rect x="0" y="560" width="{W}" height="40" fill="url(#m)"/>']
    return App("card-back", "بطاقة العمل: الظهر", W, H, svg_doc(W, H, "".join(body), "بطاقة العمل، الظهر", pattern_def("m", k.motif_soft, 60)))


def app_splash(k: AppKit, t: Typesetter) -> App:
    W, H = 1080, 1920
    body = [f'<rect width="{W}" height="{H}" fill="{k.roles["bg"]}"/>', embed(k.mark, 340, 700, 400, 400),
            f'<rect x="0" y="1600" width="{W}" height="320" fill="url(#m)"/>']
    return App("app-splash", "شاشة الافتتاح", W, H, svg_doc(W, H, "".join(body), "شاشة الافتتاح", pattern_def("m", k.motif_soft, 240)))


APPS: tuple[Callable[[AppKit, Typesetter], App], ...] = (
    print_header, letterhead, social_avatar, social_cover, social_post, slide_title, slide_content, card_front, card_back, app_splash,
)
BOARD_APPS = (social_post, slide_title)  # ما تعرضه لوحة الاتجاه


def email_signature(k: AppKit, heading_family: str, body_family: str, mark_png: str) -> str:
    r = k.roles
    f = f"'{body_family}', Tahoma, Arial, sans-serif"
    return (f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>توقيع البريد</title></head><body>'
            f'<table role="presentation" dir="rtl" cellpadding="0" cellspacing="0" style="font-family:{f};color:{r["text"]};border-collapse:collapse">'
            f'<tr><td style="padding:0 0 0 16px;vertical-align:top"><img src="{escape(mark_png)}" width="64" height="64" alt="{escape(k.name_ar)}"></td>'
            f'<td style="border-right:3px solid {r["brand"]};padding:0 14px 0 0;vertical-align:top">'
            f'<div style="font-family:\'{heading_family}\',{f};font-size:18px;font-weight:700;line-height:1.4">الاسم الكامل</div>'
            f'<div style="font-size:14px;color:{r["text_muted"]};line-height:1.7">المسمّى الوظيفي · {escape(k.name_ar)}</div>'
            f'<div style="font-size:13px;line-height:1.7">البريد الإلكتروني · رقم الهاتف</div>'
            f'<div style="font-size:13px;color:{r["brand"]};line-height:1.7">{escape(k.tagline)}</div></td></tr></table></body></html>')
