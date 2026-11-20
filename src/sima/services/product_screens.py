"""شاشات المنتج من tokens الهوية: صفحة الهبوط، ومساحة العمل بالوضعين، والهاتف، والورقة المطبوعة.

صفحات HTML حقيقية بأدوار الهوية وخطوطها ونصوص منصتها الاستراتيجية، تُصوَّر بلا نافذة إلى PNG للعرض.
هي معاينة للهوية في المنتج، لا تصميم المنتج نفسه: الهيكل عام، والمحتوى من الموجز والمنصة.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field

from .brand_book import _faces, esc

SIZES = {"landing": (1440, 900), "app-light": (1440, 900), "app-dark": (1440, 900), "mobile": (390, 844), "print": (794, 1123)}
TITLES = {"landing": "صفحة الهبوط", "app-light": "مساحة العمل · فاتح", "app-dark": "مساحة العمل · داكن", "mobile": "الهاتف",
          "print": "الورقة المطبوعة · أبيض وأسود"}


@dataclass(frozen=True)
class ScreenKit:
    name_ar: str
    tagline: str
    samples: dict[str, str]
    traits: tuple[tuple[str, str], ...]
    light: dict[str, str]
    dark: dict[str, str]
    fonts: dict[str, dict]
    mark: str
    mark_white: str
    lockup: str
    lockup_white: str
    lockup_mono: str
    motif_soft: str
    radius: int = 4
    nav: tuple[str, ...] = ()
    icons: dict[str, str] = field(default_factory=dict)  # موضوع → svg (currentColor)


def _uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _vars(r: dict[str, str]) -> str:
    return ";".join(f"--{k.replace('_', '-')}:{v}" for k, v in r.items())


def _page(k: ScreenKit, base: str, w: int, h: int, r: dict[str, str], body: str, scheme: str = "light") -> str:
    hf, bf = k.fonts["heading"], k.fonts["body"]
    return f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>{esc(k.name_ar)}</title><style>
{_faces(k.fonts, base)}
:root{{{_vars(r)};--h:"{hf["family"]}",Tahoma,sans-serif;--b:"{bf["family"]}",Tahoma,sans-serif;--hw:{hf["weight"]};--bw:{bf["weight"]};
--r:{k.radius}px;color-scheme:{scheme}}}
*{{box-sizing:border-box}}html,body{{margin:0;inline-size:{w}px;block-size:{h}px;overflow:hidden}}
body{{background:var(--bg);color:var(--text);font:var(--bw) 16px/1.7 var(--b)}}
h1,h2,h3,b.h{{font-family:var(--h);font-weight:var(--hw);line-height:1.3;margin:0}}
svg{{display:block}}.lock svg{{block-size:100%;inline-size:auto;max-inline-size:100%}}
.btn{{display:inline-flex;align-items:center;gap:8px;padding:12px 22px;border-radius:var(--r);font:600 16px/1.2 var(--b);border:1px solid transparent}}
.pri{{background:var(--brand);color:var(--on-brand)}}.sec{{background:transparent;color:var(--text);border-color:var(--border-strong)}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:calc(var(--r) * 2);padding:20px}}
.muted{{color:var(--text-muted)}}.ic{{inline-size:22px;block-size:22px;flex:none}}.ic svg{{inline-size:100%;block-size:100%}}
.chip{{display:inline-block;padding:2px 10px;border-radius:999px;background:var(--accent-soft);color:var(--text);font-size:13px}}
.field{{display:flex;flex-direction:column;gap:6px;font-size:14px}}.field span{{color:var(--text-muted)}}
.input{{block-size:44px;border:1px solid var(--border-strong);border-radius:var(--r);background:var(--bg);padding:0 12px;display:flex;align-items:center}}
.motif{{background-image:url("{_uri(k.motif_soft)}");background-size:140px auto}}
</style></head><body>{body}</body></html>"""


def _icon(k: ScreenKit, subject: str) -> str:
    svg = k.icons.get(subject)
    return f'<span class="ic">{svg}</span>' if svg else '<span class="ic" style="border:2px solid currentColor;border-radius:4px"></span>'


def landing(k: ScreenKit, base: str) -> str:
    w, h = SIZES["landing"]
    s = k.samples
    feats = "".join(f'<div class="card"><b class="h" style="font-size:20px;color:var(--brand-text)">{esc(t)}</b><p class="muted" style="margin:.4em 0 0">{esc(m)}</p></div>'
                    for t, m in k.traits[:3])
    body = f"""<header style="display:flex;align-items:center;justify-content:space-between;padding:28px 72px;border-bottom:1px solid var(--border)">
<div class="lock" style="block-size:44px">{k.lockup}</div>
<nav style="display:flex;gap:32px;color:var(--text-muted);font-size:15px"><span>المزايا</span><span>كيف يعمل</span><span>الأسعار</span></nav>
<span class="btn sec" style="padding:8px 16px">تسجيل الدخول</span></header>
<main style="display:grid;grid-template-columns:1.15fr .85fr;block-size:{h - 101}px">
<section style="padding:96px 72px 0;display:flex;flex-direction:column;gap:28px">
<span class="chip">{esc(k.tagline)}</span>
<h1 style="font-size:56px;max-inline-size:14ch">{esc(s.get("headline", k.tagline))}</h1>
<div style="display:flex;gap:12px"><span class="btn pri">{esc(s.get("button", "ابدأ"))}</span><span class="btn sec">شاهد مثالًا</span></div>
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:24px">{feats}</div></section>
<aside class="motif" style="background-color:var(--brand-soft);display:grid;place-items:center">
<div style="inline-size:260px;block-size:260px;background:var(--bg);border-radius:calc(var(--r) * 4);display:grid;place-items:center;padding:44px;border:1px solid var(--border)">{k.mark}</div>
</aside></main>"""
    return _page(k, base, w, h, k.light, body)


def app(k: ScreenKit, base: str, dark: bool) -> str:
    w, h = SIZES["app-dark" if dark else "app-light"]
    r = k.dark if dark else k.light
    s = k.samples
    nav = list(k.nav[:6]) or ["الرئيسية", "المشاريع", "القوالب", "الإعدادات"]
    items = "".join(f'<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:var(--r);'
                    f'{"background:var(--brand-soft);color:var(--text);font-weight:700" if i == 0 else "color:var(--text-muted)"}">'
                    f'{_icon(k, n)}<span>{esc(n)}</span></div>' for i, n in enumerate(nav))
    rows = "".join(f'<div class="card" style="display:flex;align-items:center;gap:14px;padding:14px 18px">{_icon(k, nav[i % len(nav)])}'
                   f'<div style="flex:1"><b>{esc(nav[i % len(nav)])} {i + 1}</b><div class="muted" style="font-size:13px">آخر تعديل قبل {i + 2} ساعات</div></div>'
                   f'<span class="chip">{"جاهز" if i % 2 == 0 else "مسودة"}</span></div>' for i in range(3))
    body = f"""<div style="display:grid;grid-template-columns:1fr 280px;block-size:{h}px">
<main style="padding:40px 48px;display:flex;flex-direction:column;gap:24px;order:1">
<div style="display:flex;align-items:center;justify-content:space-between"><h2 style="font-size:32px">{esc(nav[0])}</h2>
<span class="btn pri">{esc(s.get("button", "إنشاء"))}</span></div>
<div class="card" style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">
<label class="field"><span>الحقل الأول</span><div class="input">اختر…</div></label>
<label class="field"><span>الحقل الثاني</span><div class="input">اختر…</div></label>
<label class="field"><span>العدد</span><div class="input" style="outline:3px solid var(--focus);outline-offset:1px">12</div></label></div>
<div role="alert" style="display:flex;gap:12px;align-items:start;padding:14px 18px;border-radius:var(--r);background:var(--error-soft);color:var(--error);border-inline-start:4px solid var(--error)">
<b style="flex:none">تنبيه</b><span>{esc(s.get("error", ""))}</span></div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;flex:1">
<div style="display:flex;flex-direction:column;gap:10px">{rows}</div>
<div class="card motif" style="display:grid;place-items:center;text-align:center;background-color:var(--surface)">
<div style="background:var(--bg);padding:24px 28px;border-radius:calc(var(--r) * 2);border:1px solid var(--border);max-inline-size:340px">
<div style="inline-size:56px;margin:0 auto 12px">{k.mark}</div><p class="muted" style="margin:0">{esc(s.get("empty_state", ""))}</p></div></div></div></main>
<aside style="background:var(--surface);border-inline-start:1px solid var(--border);padding:28px 18px;display:flex;flex-direction:column;gap:6px;order:0">
<div class="lock" style="block-size:36px;margin:0 8px 24px">{k.lockup_white if dark else k.lockup}</div>{items}
<div style="margin-top:auto;display:flex;align-items:center;gap:10px;padding:10px"><span style="inline-size:36px;block-size:36px;border-radius:50%;background:var(--accent)"></span>
<div><b style="font-size:14px">الاسم الكامل</b><div class="muted" style="font-size:12px">{esc(k.name_ar)}</div></div></div></aside></div>"""
    return _page(k, base, w, h, r, body, "dark" if dark else "light")


def mobile(k: ScreenKit, base: str) -> str:
    w, h = SIZES["mobile"]
    s = k.samples
    nav = list(k.nav[:3]) or ["الأول", "الثاني", "الثالث"]
    cards = "".join(f'<div class="card" style="display:flex;gap:12px;align-items:center;padding:14px">{_icon(k, n)}<div style="flex:1"><b>{esc(n)}</b>'
                    f'<div class="muted" style="font-size:13px">{esc(k.tagline)}</div></div></div>' for n in nav)
    body = f"""<div style="display:flex;flex-direction:column;block-size:{h}px">
<div style="block-size:44px"></div>
<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 20px"><div class="lock" style="block-size:30px">{k.lockup}</div>
<span style="inline-size:32px;block-size:32px;border-radius:50%;background:var(--accent)"></span></div>
<div style="margin:16px 20px;padding:28px 22px;border-radius:calc(var(--r) * 3);background:var(--brand);color:var(--on-brand)">
<h2 style="font-size:28px;color:var(--on-brand)">{esc(s.get("headline", k.tagline))}</h2>
<span class="btn" style="margin-top:18px;background:var(--bg);color:var(--brand-text)">{esc(s.get("button", "ابدأ"))}</span></div>
<div style="padding:0 20px;display:flex;flex-direction:column;gap:12px">{cards}</div>
<nav style="margin-top:auto;display:flex;justify-content:space-around;padding:12px 0 30px;border-top:1px solid var(--border);background:var(--surface)">
{"".join(f'<span style="display:flex;flex-direction:column;align-items:center;gap:4px;font-size:12px;color:{"var(--brand)" if i == 0 else "var(--text-muted)"}">{_icon(k, n)}{esc(n)}</span>' for i, n in enumerate(nav))}</nav></div>"""
    return _page(k, base, w, h, k.light, body)


def printed(k: ScreenKit, base: str) -> str:
    w, h = SIZES["print"]
    bw = {**k.light, "bg": "#FFFFFF", "text": "#000000", "text_muted": "#333333", "border": "#000000"}
    lines = "".join(f'<div style="display:flex;gap:14px;align-items:baseline;margin-bottom:22px"><b>{i + 1}.</b><div style="flex:1">'
                    f'<div style="block-size:10px;background:#000;inline-size:{70 - (i * 9) % 30}%;margin-bottom:12px"></div>'
                    f'<div style="block-size:2px;background:#000;opacity:1;inline-size:100%;margin-top:34px"></div></div></div>' for i in range(6))
    body = f"""<div style="padding:48px 56px;display:flex;flex-direction:column;block-size:{h}px">
<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #000;padding-bottom:16px">
<div class="lock" style="block-size:48px">{k.lockup_mono}</div>
<div style="display:flex;flex-direction:column;gap:10px;font-size:14px;min-inline-size:300px">
{"".join(f'<div style="display:flex;gap:10px"><span>{x}</span><span style="flex:1;border-bottom:1.5px solid #000"></span></div>' for x in ("الاسم:", "الصف:", "التاريخ:"))}</div></div>
<h2 style="font-size:24px;margin:28px 0 24px">عنوان الورقة</h2>{lines}
<div style="margin-top:auto;display:flex;justify-content:space-between;font-size:12px;border-top:1.5px solid #000;padding-top:10px">
<span>{esc(k.tagline)}</span><span>١ / ١</span></div></div>"""
    return _page(k, base, w, h, bw, body)


def screens(k: ScreenKit, base: str) -> dict[str, str]:
    """اسم الشاشة → HTML. base: مسار الخطوط نسبةً إلى مجلد الشاشات."""
    return {"landing": landing(k, base), "app-light": app(k, base, False), "app-dark": app(k, base, True), "mobile": mobile(k, base),
            "print": printed(k, base)}
