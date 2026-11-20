"""ورقة معاينة HTML واحدة: المفاهيم الخمسة بالأحجام والمعالجات وسياقات بوابة المالك الفعلية."""
from __future__ import annotations

import base64
import html
import re
from pathlib import Path

from ..domain import FAMILY_AR, MEDIUM_AR, Brief, Concept
from . import svgtools
from .audit import AuditReport
from .colorize import colorize

_CSS = """
:root{--paper:%(paper)s;--ink:%(ink)s;--brand:%(brand)s;--accent:%(accent)s;--line:#e2dcd0;--muted:#6b6f76;--ok:#2d7046;--warn:#a87b26;--bad:#a3312a}
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI","Noto Sans Arabic",Tahoma,sans-serif;background:#fafaf8;color:#1b1e23;line-height:1.7}
header{padding:20px 28px;border-block-end:1px solid var(--line);background:#fff}h1{margin:0;font-size:22px}h2{font-size:18px;margin:36px 0 10px}h3{font-size:14px;color:var(--muted);margin:16px 0 6px}
main{padding:0 28px 60px;max-inline-size:1280px;margin:0 auto}.muted{color:var(--muted);font-size:13px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:20px;margin-block:18px}
.row{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-end}.col{display:flex;flex-direction:column;gap:6px;align-items:center}
.tile{display:inline-flex;align-items:center;justify-content:center;border:1px solid var(--line);background:#fff}
.tile.dark{background:#111}.tile img,.tile svg{display:block}
.px{image-rendering:pixelated;image-rendering:crisp-edges}
.status{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;color:#fff}.status.ok{background:var(--ok)}.status.warn{background:var(--warn)}.status.bad{background:var(--bad)}
ul.f{margin:6px 0;padding-inline-start:20px;font-size:13px}
.ctx{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.portal{background:var(--paper);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.portal .bar{display:flex;align-items:center;gap:10px;padding:10px 14px;border-block-end:1px solid var(--line);background:#fff}
.portal .bar .t{font-weight:600;font-size:15px;color:var(--ink)}.portal .body{padding:14px;background-image:linear-gradient(rgba(27,30,35,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(27,30,35,.05) 1px,transparent 1px);background-size:16px 16px;min-block-size:70px}
.tab{background:#dee1e6;padding:8px 10px 0;border-radius:8px 8px 0 0;display:flex;gap:8px;align-items:center;inline-size:260px}
.tab .tb{background:#fff;border-radius:8px 8px 0 0;padding:6px 12px;display:flex;align-items:center;gap:8px;font-size:12px;flex:1;direction:ltr}
.dark-side{background:#1b1e23;color:#f1ede5;padding:14px;border-radius:8px;display:flex;gap:10px;align-items:center}
.print{background:#fff;border:1px solid #ccc;padding:14px 18px;font-family:"Sakkal Majalla",Arial,sans-serif;display:flex;justify-content:space-between;align-items:center;box-shadow:0 1px 3px rgba(0,0,0,.1)}
.phone{background:linear-gradient(160deg,#eef1f5,#d9dee6);padding:14px;border-radius:14px;display:flex;gap:16px;align-items:center}
.phone .app{inline-size:56px;block-size:56px;border-radius:14px;background:var(--brand);display:flex;align-items:center;justify-content:center}
.shelf{display:flex;gap:24px;align-items:center;flex-wrap:wrap;padding:10px 0}
.cmp{display:flex;gap:26px;align-items:center;flex-wrap:wrap}
code{background:#f1ede5;padding:2px 6px;border-radius:4px;font-size:13px;direction:ltr;display:inline-block}
table{border-collapse:collapse;font-size:13px}td,th{border:1px solid var(--line);padding:4px 10px;text-align:start}
"""


def _inline(svg: str, key: str, size: int | None = None, w: int | None = None, h: int | None = None) -> str:
    """تضمين SVG مباشرة مع تمييز المعرفات لتعايش عدة ملفات."""
    s = re.sub(r"<\?xml[^>]*\?>", "", svg)
    s = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{key}-{m.group(1)}"', s)
    s = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{key}-{m.group(1)})", s)
    s = re.sub(r'\b(width|height)="[^"]*"', "", s, count=2)
    if size is not None:
        w = h = size
    attrs = ""
    if w is not None:
        attrs += f' width="{w}"'
    if h is not None:
        attrs += f' height="{h}"'
    return s.replace("<svg", f"<svg{attrs}", 1)


def _png(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def _status(rep: AuditReport | None) -> str:
    if rep is None:
        return '<span class="status bad">لم يُفحص</span>'
    if not rep.passed:
        return '<span class="status bad">فشل الفحص</span>'
    if rep.warnings:
        return '<span class="status warn">نجح مع تنبيهات</span>'
    return '<span class="status ok">نجح</span>'


def build_preview(brief: Brief, version: int, key: str, concepts: list[Concept], svgs: dict[str, str],
                  renders: dict[str, dict[str, str]], audits: dict[str, AuditReport],
                  wordmark_svg: str | None, lockups: dict[str, str], decide_cmd: str,
                  smalls: dict[str, str] | None = None) -> str:
    smalls = smalls or {}
    pal = brief.palette
    css = _CSS % {"paper": pal.paper, "ink": pal.ink, "brand": pal.brand, "accent": pal.accent or pal.brand}
    e = html.escape
    parts = [f"<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>سِمة: {e(brief.name_ar)} v{version}</title><style>{css}</style></head><body>",
             f"<header><h1>ورقة معاينة: {e(brief.name_ar)} <span class='muted'>v{version} · {e(key)}</span></h1>",
             f"<div class='muted'>الإحساس المطلوب: {e(brief.taste.feeling)} · الكلمات الثلاث: {e('، '.join(brief.three_words))}</div></header><main>"]
    parts.append("<h2>المقارنة جنبًا إلى جنب (48 بكسل، أبيض وأسود)</h2><div class='card'><div class='cmp'>")
    for c in concepts:
        if c.id in svgs:
            parts.append(f"<div class='col'>{_inline(svgs[c.id], c.id + '-cmp', 48)}<span class='muted'>{e(c.id)}</span></div>")
    parts.append("</div></div>")
    for c in concepts:
        svg = svgs.get(c.id)
        if not svg:
            continue
        rep = audits.get(c.id)
        r = renders.get(c.id, {})
        small = smalls.get(c.id)
        icon_src = small or svg  # الأيقونات من الرمز المصغّر إن وُجد
        color_svg = colorize(icon_src, pal.brand, pal.accent)
        rev_svg = svgtools.reversed_(icon_src, ink="#FFFFFF", background="#1b1e23")
        parts.append(f"<div class='card' id='{e(c.id)}'><h2 style='margin-top:0'>{e(c.id)} · {e(c.name)} <span class='muted'>{e(FAMILY_AR[c.family])} · {e(MEDIUM_AR[c.medium])}</span> {_status(rep)}</h2>")
        parts.append(f"<p>{e(c.sentence)}</p>")
        if c.reference:
            parts.append(f"<p class='muted'>المرجع: {e(c.reference)}</p>")
        parts.append("<h3>الأحجام (تصيير المتصفح) ومنظر البكسل عند 16</h3><div class='row'>")
        parts.append(f"<div class='col'><span class='tile'>{_inline(svg, c.id + '-l', 256)}</span><span class='muted'>256</span></div>")
        for s in (48, 32, 16):
            parts.append(f"<div class='col'><span class='tile' style='inline-size:64px;block-size:64px'>{_inline(svg, f'{c.id}-s{s}', s)}</span><span class='muted'>{s}</span></div>")
        if r.get("16"):
            parts.append(f"<div class='col'><span class='tile'><img class='px' src='{_png(r['16'])}' width='128' height='128' alt=''></span><span class='muted'>16 مكبَّرة ×8</span></div>")
        if small:
            srep = audits.get(c.id + "-small")
            sr = renders.get(c.id + "-small", {})
            parts.append(f"</div><h3>الرمز المصغّر للأيقونات {_status(srep)}</h3><div class='row'>")
            parts.append(f"<div class='col'><span class='tile'>{_inline(small, c.id + '-sm', 128)}</span><span class='muted'>128</span></div>")
            for s in (48, 32, 16):
                parts.append(f"<div class='col'><span class='tile' style='inline-size:64px;block-size:64px'>{_inline(small, f'{c.id}-sm{s}', s)}</span><span class='muted'>{s}</span></div>")
            if sr.get("16"):
                parts.append(f"<div class='col'><span class='tile'><img class='px' src='{_png(sr['16'])}' width='128' height='128' alt=''></span><span class='muted'>16 مكبَّرة ×8</span></div>")
            if srep and (srep.findings or srep.warnings):
                parts.append("<ul class='f'>" + "".join(f"<li style='color:var(--bad)'>{e(f)}</li>" for f in srep.findings) + "".join(f"<li style='color:var(--warn)'>{e(w)}</li>" for w in srep.warnings) + "</ul>")
        parts.append("</div><h3>المعالجات: أحادي، معكوس، ممرآة، مشوّش</h3><div class='row'>")
        for name, label in (("mono", "أحادي"), ("reversed", "معكوس"), ("mirrored", "ممرآة"), ("blurred", "مشوّش")):
            if r.get(name):
                dark = " dark" if name == "reversed" else ""
                parts.append(f"<div class='col'><span class='tile{dark}'><img src='{_png(r[name])}' width='128' height='128' alt=''></span><span class='muted'>{label}</span></div>")
        parts.append("</div>")
        # السياقات الفعلية
        parts.append("<h3>السياقات الفعلية</h3><div class='ctx'>")
        lock = lockups.get(c.id)
        lock_html = _inline(colorize(lock, pal.brand, pal.accent), c.id + "-lk", h=36) if lock else _inline(color_svg, c.id + "-hd", 36)
        parts.append(f"<div class='portal'><div class='bar'>{lock_html}<span class='t'>{e(brief.name_ar)}</span></div><div class='body'><span class='muted'>ترويسة البوابة على ورق المربعات</span></div></div>")
        parts.append(f"<div><div class='tab'><div class='tb'>{_inline(color_svg, c.id + '-fav', 16)}<span>{e(brief.name_latin or brief.name_ar)}</span></div></div><div class='muted'>لسان المتصفح (16 بكسل)</div></div>")
        parts.append(f"<div class='dark-side'>{_inline(rev_svg, c.id + '-dk', 40)}<div><div style='font-weight:600'>{e(brief.wordmark_text)}</div><div class='muted' style='color:#c9c0b0'>الوضع الداكن / الشريط الجانبي</div></div></div>")
        parts.append(f"<div class='print'><div><div style='font-size:15px;font-weight:700'>{e(brief.name_ar)}</div><div style='font-size:12px'>ورقة عمل: الوحدة الثالثة</div></div>{_inline(svgtools.mono(svg), c.id + '-pr', h=44, w=(140 if small else 44))}</div>")
        parts.append(f"<div class='phone'><div class='app'>{_inline(svgtools.mono(svg, '#FFFFFF'), c.id + '-ap', 36)}</div><div><div style='font-weight:600'>{e(brief.wordmark_text)}</div><div class='muted'>أيقونة التطبيق 56 بكسل</div></div></div>")
        parts.append("</div>")
        if rep:
            parts.append("<h3>الفحص الآلي</h3>")
            m = rep.metrics
            parts.append(f"<table><tr><th>أصغر سماكة عند {m.get('base_size', 16)}</th><th>تغطية صغير/256</th><th>مكوّنات صغير</th><th>نقاط الارتكاز</th><th>تباين الحبر</th><th>أقرب مرجع</th></tr>")
            sim = m.get("similarity") or []
            simtxt = "، ".join(f"{s['brand']} ({s['distance']})" for s in sim[:3]) if sim else "لا مكتبة"
            parts.append(f"<tr><td>{m.get('min_stroke_px', '؟')}</td><td>{m.get('coverage_ratio', '؟')}</td><td>{m.get('components_small', '؟')}</td><td>{m.get('anchors', '؟')}</td><td>{m.get('contrast_ink_on_paper', '؟')}:1</td><td>{e(simtxt)}</td></tr></table>")
            if rep.findings:
                parts.append("<ul class='f'>" + "".join(f"<li style='color:var(--bad)'>{e(f)}</li>" for f in rep.findings) + "</ul>")
            if rep.warnings:
                parts.append("<ul class='f'>" + "".join(f"<li style='color:var(--warn)'>{e(w)}</li>" for w in rep.warnings) + "</ul>")
        parts.append("</div>")
    if wordmark_svg:
        parts.append(f"<h2>العلامة الكلامية «{e(brief.wordmark_text)}» (مسارات، بلا نص حي)</h2><div class='card'>{_inline(wordmark_svg, 'wm', h=96)}</div>")
    parts.append(f"<h2>القرار</h2><div class='card'><p>اعتماد مفهوم: <code>{e(decide_cmd)} --approve &lt;id&gt; --reason \"...\"</code></p>"
                 f"<p>رفض مفهوم: <code>{e(decide_cmd)} --reject &lt;id&gt; --reason \"...\"</code> (يُعاد رسمه بسببك في الوسيط نفسه ثم يعود إلى الحَكَم)</p>"
                 f"<p>طلب تعديل: <code>{e(decide_cmd)} --revise &lt;id&gt; --reason \"...\"</code></p></div>")
    parts.append("</main></body></html>")
    return "".join(parts)
