"""عرض الكشف: شرائح 16:9 سردية على طريقة الوكالات — السياق، فالمنصة، فالفكرة، فالرمز وبناؤه، فالنظام، فالهوية في الحياة، فالقرار.

وضعان: «directions» يعرض الاتجاهات الثلاثة فصولًا متوازية بالسياقات نفسها للمقارنة، و«final» يعرض الاتجاه المعتمد كاملًا.
صفحة واحدة بلا مكتبات: تمرير بالأسهم ولوحة المفاتيح، وتُطبع PDF شريحةً في كل صفحة (1920×1080).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.identity import CheckReport, Direction, Strategy
from .brand_book import ROLE_AR, _faces, esc
from .color_system import hex_to_linear
from .product_screens import TITLES

KEY_ROLES = ("brand", "accent", "bg", "text")


@dataclass(frozen=True)
class Chapter:
    """اتجاه واحد بكل ما يلزم لعرضه."""
    direction: Direction
    system: dict
    fonts: dict
    checks: CheckReport
    mark: str          # svg ملوّن
    mark_white: str
    mark_mono: str
    lockup: str
    lockup_white: str
    motif_soft: str
    motif_strong: str
    screens: dict[str, str]          # اسم الشاشة → مسار PNG نسبي
    apps: list[tuple[str, str]] = field(default_factory=list)   # (العنوان، مسار SVG نسبي)
    icons: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Deck:
    mode: str  # directions | final
    name_ar: str
    version: int
    key: str
    purpose: str
    audience: str
    three_words: tuple[str, ...]
    strategy: Strategy
    concept: str
    chapters: list[Chapter]
    fonts_base: str
    ask: str  # ما المطلوب من المالك في الشريحة الأخيرة


def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def cmyk(h: str) -> tuple[int, int, int, int]:
    """تحويل تقريبي بلا ملف ICC؛ القيمة النهائية عند المطبعة (و Pantone ملكية لا تُحسب محليًا)."""
    r, g, b = (v / 255 for v in rgb(h))
    k = 1 - max(r, g, b)
    if k >= 1:
        return 0, 0, 0, 100
    return tuple(round(100 * x) for x in ((1 - r - k) / (1 - k), (1 - g - k) / (1 - k), (1 - b - k) / (1 - k), k))  # type: ignore[return-value]


def _lum(h: str) -> float:
    r, g, b = hex_to_linear(h)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _vars(ch: Chapter) -> str:
    r = ch.system["light"]
    f = ch.fonts
    return (f'--bg:{r["bg"]};--surface:{r["surface"]};--raised:{r["raised"]};--line:{r["border"]};--ink:{r["text"]};--muted:{r["text_muted"]};'
            f'--brand:{r["brand"]};--brand-strong:{r["brand_strong"]};--brand-soft:{r["brand_soft"]};--brand-text:{r.get("brand_text", r["brand"])};--on-brand:{r["on_brand"]};'
            f"--accent:{r['accent']};--accent-soft:{r['accent_soft']};--h:'{f['heading']['family']}',Tahoma,sans-serif;"
            f"--b:'{f['body']['family']}',Tahoma,sans-serif;--hw:{f['heading']['weight']};--bw:{f['body']['weight']}")


def _slide(body: str, ch: Chapter, cls: str = "", label: str = "") -> str:
    return f'<section class="s {cls}" style="{_vars(ch)}" aria-label="{esc(label)}">{body}</section>'


def _foot(d: Deck, ch: Chapter | None, section: str) -> str:
    tag = f" · {esc(ch.direction.id)} {esc(ch.direction.name)}" if ch and d.mode == "directions" else ""
    return f'<footer><span>{esc(d.name_ar)}{tag}</span><span>{esc(section)}</span></footer>'


# ---------- الشرائح المشتركة ----------
def cover(d: Deck, ch: Chapter) -> str:
    sub = ("ثلاثة اتجاهات للهوية" if len(d.chapters) > 1 else "اتجاه الهوية المعتمد") if d.mode == "directions" else "الهوية البصرية"
    return _slide(f"""<div class="cover"><div class="lock">{ch.lockup}</div>
<div><p class="kick">{sub} · الإصدار {d.version}</p><h1 class="xl">{esc(d.name_ar)}</h1><p class="lead">{esc(d.strategy.tagline)}</p></div></div>
<div class="motifband" style="background-image:url('{_uri(ch.motif_soft)}')"></div>""", ch, "c-cover", "الغلاف")


def context(d: Deck, ch: Chapter) -> str:
    words = "".join(f"<li>{esc(w)}</li>" for w in d.three_words)
    return _slide(f"""<p class="kick">٠١ · السياق</p><h2>لمن نصمّم، ولماذا</h2>
<div class="cols2"><div><h3>الغرض</h3><p class="lead">{esc(d.purpose)}</p><h3>الجمهور</h3><p>{esc(d.audience)}</p></div>
<div class="words"><h3>ثلاث كلمات تحكم كل قرار</h3><ol>{words}</ol></div></div>{_foot(d, None, "السياق")}""", ch, "", "السياق")


def platform(d: Deck, ch: Chapter) -> str:
    s = d.strategy
    traits = "".join(f'<div class="tcard"><b>{esc(t.trait)}</b><p>{esc(t.means)}</p><small>ليس {esc(t.not_)}</small></div>' for t in s.personality)
    return _slide(f"""<p class="kick">٠٢ · المنصة</p><h2 class="quote">{esc(s.positioning)}</h2>
<p class="lead"><b>الوعد:</b> {esc(s.promise)}</p><div class="cols3">{traits}</div>{_foot(d, None, "المنصة الاستراتيجية")}""", ch, "", "المنصة")


def voice(d: Deck, ch: Chapter) -> str:
    s = d.strategy
    samples = "".join(f'<div class="sample"><small>{esc(k)}</small><p>{esc(v)}</p></div>' for k, v in
                      zip(("عنوان", "زر", "رسالة خطأ", "حالة فارغة"), (s.samples.get(x, "") for x in ("headline", "button", "error", "empty_state")),
                          strict=True))
    return _slide(f"""<p class="kick">٠٣ · النبرة</p><h2>كيف نتكلم</h2>
<div class="cols2"><div><h3>نقول</h3><ul class="do">{"".join(f"<li>{esc(x)}</li>" for x in s.voice_do)}</ul></div>
<div><h3>لا نقول</h3><ul class="dont">{"".join(f"<li>{esc(x)}</li>" for x in s.voice_dont)}</ul></div></div>
<div class="samples">{samples}</div>{_foot(d, None, "نبرة الصوت")}""", ch, "", "النبرة")


def idea(d: Deck, ch: Chapter) -> str:
    return _slide(f"""<div class="split"><div class="pad"><p class="kick" style="color:var(--on-brand)">٠٤ · الفكرة</p>
<h2 class="quote" style="color:var(--on-brand)">{esc(d.concept)}</h2></div>
<div class="markbox">{ch.mark_white}</div></div>""", ch, "c-brand", "الفكرة")


def construction(d: Deck, ch: Chapter) -> str:
    sizes = "".join(f'<figure><div style="inline-size:{px}px">{ch.mark}</div><figcaption>{px} بكسل</figcaption></figure>' for px in (16, 24, 32, 48, 64))
    return _slide(f"""<p class="kick">٠٥ · الرمز</p><h2>البناء والمساحة الخالية</h2>
<div class="cols2"><div class="clear"><div class="zone"><div class="grid"></div>{ch.mark}</div>
<p class="note">المساحة الخالية حول الرمز لا تقل عن ربع عرضه؛ لا نص ولا صورة ولا حافة داخلها.</p></div>
<div><h3>يبقى مقروءًا من 16 بكسل</h3><div class="sizes">{sizes}</div>
<h3 style="margin-top:2.2cqw">على كل خلفية</h3><div class="bgs"><div style="background:var(--bg)">{ch.mark}</div>
<div style="background:var(--brand)">{ch.mark_white}</div><div style="background:#fff">{ch.mark_mono}</div><div style="background:#111">{ch.mark_white}</div></div></div></div>
{_foot(d, ch, "الرمز")}""", ch, "", "بناء الرمز")


def misuse(d: Deck, ch: Chapter) -> str:
    bad = [("لا تمدّه", "transform:scaleX(1.45)"), ("لا تدوّره", "transform:rotate(-14deg)"), ("لا تغيّر ألوانه", "filter:hue-rotate(150deg)"),
           ("لا تضعه على خلفية مزدحمة", "")]
    cells = "".join(f'<figure class="bad"><div class="m" style="{css}">{ch.mark}</div><figcaption>{esc(t)}</figcaption></figure>' for t, css in bad[:3])
    cells += (f'<figure class="bad"><div class="m busy" style="background-image:url(\'{_uri(ch.motif_strong)}\');background-color:var(--brand)">'
              f'{ch.mark}</div><figcaption>{esc(bad[3][0])}</figcaption></figure>')
    return _slide(f"""<p class="kick">٠٦ · الرمز</p><h2>ما لا يُفعل به</h2><div class="cols4">{cells}</div>
<p class="note">الأصول الرسمية في مجلد الحزمة وحدها مرجع؛ أي صيغة غير موجودة فيها تُطلب ولا تُرسم.</p>{_foot(d, ch, "الاستعمالات الممنوعة")}""",
                  ch, "", "الاستعمالات الممنوعة")


def color(d: Deck, ch: Chapter) -> str:
    r = ch.system["light"]
    weights = {"bg": 40, "brand": 28, "text": 18, "accent": 8, "brand_soft": 6}
    bar = "".join(f'<i style="flex:{w};background:{r[k]}"></i>' for k, w in weights.items())
    cards = []
    for k in ("brand", "accent", "bg", "text"):
        h = r[k]
        fg = "#000" if _lum(h) > 0.35 else "#fff"
        c, m, y, kk = cmyk(h)
        cards.append(f'<div class="swatch" style="background:{h};color:{fg}"><b>{esc(ROLE_AR[k])}</b>'
                     f'<span>HEX {h}</span><span>RGB {" ".join(map(str, rgb(h)))}</span><span>CMYK {c} {m} {y} {kk} *</span></div>')
    return _slide(f"""<p class="kick">٠٧ · اللون</p><h2>اللون بنسبه</h2><div class="propbar">{bar}</div>
<div class="cols4">{"".join(cards)}</div>
<p class="note">* CMYK تقريبي بلا ملف ICC؛ يُطابَق عند المطبعة، وPantone يُختار هناك. تدرجات 50..950 والوضع الداكن في tokens.</p>
{_foot(d, ch, "اللون")}""", ch, "", "اللون")


def typography(d: Deck, ch: Chapter) -> str:
    f = ch.fonts
    dd = ch.direction
    nums = "١٢٣٤٥٦٧٨٩٠" if dd.numerals == "arab" else "1234567890"
    return _slide(f"""<p class="kick">٠٨ · الطباعة</p><div class="cols2"><div><div class="spec">أبجد</div>
<p class="muted">{esc(f["heading"]["family"])} {f["heading"]["weight"]} للعناوين، و{esc(f["body"]["family"])} {f["body"]["weight"]} للنص</p></div>
<div><h2 style="font-size:3.4cqw">{esc(d.strategy.samples.get("headline", d.strategy.tagline))}</h2>
<p class="lead" style="font-family:var(--b)">{esc(d.strategy.positioning)}</p><p class="nums">{nums}</p></div></div>
{_foot(d, ch, "الطباعة")}""", ch, "", "الطباعة")


def visual(d: Deck, ch: Chapter) -> str:
    icons = "".join(f'<figure class="icon"><div>{i["svg"]}</div><figcaption>{esc(i["subject"])}</figcaption></figure>' for i in ch.icons[:10])
    return _slide(f"""<div class="split"><div class="pad"><p class="kick">٠٩ · اللغة البصرية</p><h2>{esc(ch.direction.name)}</h2>
<p class="lead">{esc(ch.direction.motif_rule)}</p>{f'<div class="icons">{icons}</div>' if icons else ""}</div>
<div class="motiffull" style="background-image:url('{_uri(ch.motif_strong)}')"></div></div>""", ch, "", "اللغة البصرية")


def in_life(d: Deck, ch: Chapter) -> list[str]:
    s = ch.screens
    out = []
    if "landing" in s:
        out.append(_slide(f"""<p class="kick">١٠ · في الحياة</p><h2>الموقع</h2><div class="browser"><div class="bar"><i></i><i></i><i></i></div>
<img src="{esc(s["landing"])}" alt="{esc(TITLES["landing"])}"></div>{_foot(d, ch, "الهوية في الحياة")}""", ch, "", "الموقع"))
    if "app-light" in s and "app-dark" in s:
        out.append(_slide(f"""<p class="kick">١١ · في الحياة</p><h2>المنتج بالوضعين</h2><div class="pair">
<div class="browser"><img src="{esc(s["app-light"])}" alt="{esc(TITLES["app-light"])}"></div>
<div class="browser"><img src="{esc(s["app-dark"])}" alt="{esc(TITLES["app-dark"])}"></div></div>{_foot(d, ch, "الهوية في الحياة")}""", ch, "", "المنتج"))
    phone = f'<div class="phone"><img src="{esc(s["mobile"])}" alt="{esc(TITLES["mobile"])}"></div>' if "mobile" in s else ""
    paper = f'<div class="paper"><img src="{esc(s["print"])}" alt="{esc(TITLES["print"])}"></div>' if "print" in s else ""
    apps = "".join(f'<figure class="app"><img src="{esc(p)}" alt="{esc(t)}"><figcaption>{esc(t)}</figcaption></figure>' for t, p in ch.apps[:4])
    out.append(_slide(f"""<p class="kick">١٢ · في الحياة</p><h2>الهاتف والورق والتواصل</h2><div class="life">{phone}{paper}<div class="apps">{apps}</div></div>
{_foot(d, ch, "الهوية في الحياة")}""", ch, "", "الهاتف والورق"))
    return out


def why(d: Deck, ch: Chapter) -> str:
    rep = ch.checks
    passed = sum(1 for c in rep.checks if c.ok)
    warns = [c for c in rep.checks if not c.ok and not c.blocking]
    rows = "".join(f'<li><b>{esc(w)}</b></li>' for w in d.three_words)
    return _slide(f"""<p class="kick">١٣ · لماذا تنجح</p><h2 class="quote">{esc(ch.direction.idea)}</h2>
<div class="cols2"><div><h3>تخدم الكلمات الثلاث</h3><ul class="do">{rows}</ul></div>
<div class="stat"><b>{passed}<small>/{len(rep.checks)}</small></b><p>فحصًا آليًا ناجحًا: التباين في الوضعين، وعمى الألوان، وتغطية الخطوط، وسياسة الألوان.</p>
{"".join(f'<p class="note">ملاحظة: {esc(c.name)} — {esc(c.detail)}</p>' for c in warns[:2])}</div></div>{_foot(d, ch, "الأساس")}""", ch, "", "لماذا تنجح")


# ---------- وضع الاتجاهات ----------
def divider(d: Deck, ch: Chapter, i: int) -> str:
    return _slide(f"""<div class="split"><div class="pad"><p class="kick" style="color:var(--on-brand)">الاتجاه {i}</p>
<h1 class="xl" style="color:var(--on-brand)">{esc(ch.direction.name)}</h1><p class="lead" style="color:var(--on-brand)">{esc(ch.direction.idea)}</p></div>
<div class="motiffull" style="background-image:url('{_uri(ch.motif_strong)}')"></div></div>""", ch, "c-brand", f"الاتجاه {ch.direction.id}")


def system_slide(d: Deck, ch: Chapter) -> str:
    r = ch.system["light"]
    sw = "".join(f'<div class="swatch" style="background:{r[k]};color:{"#000" if _lum(r[k]) > 0.35 else "#fff"}"><b>{esc(ROLE_AR[k])}</b><span>{r[k]}</span></div>'
                 for k in KEY_ROLES)
    f = ch.fonts
    return _slide(f"""<p class="kick">{esc(ch.direction.id)} · النظام</p><div class="cols2"><div><div class="spec" style="font-size:9cqw">أبجد</div>
<p class="muted">{esc(f["heading"]["family"])} للعناوين، و{esc(f["body"]["family"])} للنص</p><div class="cols4 small">{sw}</div></div>
<div class="motifpanel" style="background-image:url('{_uri(ch.motif_soft)}')"><div class="lock">{ch.lockup}</div></div></div>
{_foot(d, ch, "اللون والطباعة والنمط")}""", ch, "", f"نظام {ch.direction.id}")


def compare(d: Deck) -> str:
    ch0 = d.chapters[0]
    cols = "".join(f"""<div class="cmp" style="{_vars(ch)}"><div class="cmpimg"><img src="{esc(ch.screens.get("landing", ""))}" alt="الموقع بالاتجاه {esc(ch.direction.id)}"></div>
<b>{esc(ch.direction.id)} · {esc(ch.direction.name)}</b><span class="dots">{"".join(f'<i style="background:{ch.system["light"][k]}"></i>' for k in KEY_ROLES)}</span>
<p>{esc(ch.direction.idea)}</p></div>""" for ch in d.chapters)
    return _slide(f'<p class="kick">المقارنة</p><h2>ثلاثة اتجاهات، سياق واحد</h2><div class="cols3">{cols}</div>{_foot(d, None, "المقارنة")}',
                  ch0, "", "المقارنة")


def decision(d: Deck, ch: Chapter) -> str:
    return _slide(f"""<div class="center"><p class="kick">القرار</p><h1 class="xl">{esc(d.ask)}</h1>
<p class="lead">القرار من صفحة «اليوم» في منصة سِمة؛ مربوط بهذا الإصدار ومفتاحه <bdi>{esc(d.key)}</bdi>، وأي تعديل بعده يعيده إليك.</p></div>""",
                  ch, "", "القرار")


def _uri(svg: str) -> str:
    import base64
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


CSS = """
*{box-sizing:border-box}html,body{margin:0;background:#0d0d0f}body{scroll-snap-type:y mandatory;overflow-y:auto;block-size:100vh}
.s{position:relative;inline-size:min(100vw,177.78vh);aspect-ratio:16/9;margin:0 auto 2vh;overflow:hidden;scroll-snap-align:center;
container-type:inline-size;background:var(--bg);color:var(--ink);font:var(--bw) 1.25cqw/1.7 var(--b);padding:5cqw 6cqw 6cqw;display:flex;flex-direction:column}
h1,h2,h3{font-family:var(--h);font-weight:var(--hw);line-height:1.3;margin:0 0 .5em}h2{font-size:3.2cqw;max-inline-size:40ch}h3{font-size:1.5cqw;color:var(--brand-text)}
.xl{font-size:6cqw;line-height:1.2}.lead{font-size:1.7cqw;line-height:1.7;max-inline-size:60ch}.kick{font-size:1.05cqw;color:var(--brand-text);font-weight:700;margin:0 0 1cqw}
.quote{font-size:2.5cqw;line-height:1.5;max-inline-size:36ch}.muted{color:var(--muted)}.note{color:var(--muted);font-size:1.05cqw;margin-top:auto}
p{margin:0 0 1cqw}footer{position:absolute;inset-inline:6cqw;inset-block-end:2.2cqw;display:flex;justify-content:space-between;font-size:.9cqw;color:var(--muted)}
svg{display:block;max-inline-size:100%;block-size:auto}img{display:block;max-inline-size:100%}
.cols2{display:grid;grid-template-columns:1fr 1fr;gap:4cqw;align-items:start;flex:1}.cols3{display:grid;grid-template-columns:repeat(3,1fr);gap:2cqw}
.cols4{display:grid;grid-template-columns:repeat(4,1fr);gap:1.5cqw}
.c-cover{justify-content:center}.cover{display:grid;grid-template-columns:1fr 1fr;gap:6cqw;align-items:center;flex:1}.cover .lock svg{inline-size:100%}
.motifband{position:absolute;inset-inline:0;inset-block-end:0;block-size:7cqw;background-size:7cqw auto}
.c-brand{background:var(--brand);color:var(--on-brand);padding:0}.split{display:grid;grid-template-columns:1.1fr .9fr;block-size:100%}
.split .pad{padding:6cqw;display:flex;flex-direction:column;justify-content:center}.markbox{display:grid;place-items:center;padding:8cqw;background:var(--brand-strong)}
.markbox svg{inline-size:22cqw}.motiffull{background-size:9cqw auto;background-color:var(--brand)}
.s:not(.c-brand) .split{margin:-5cqw -6cqw -6cqw;block-size:calc(100% + 11cqw)}
.words ol{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:1.4cqw}
.words li{font-family:var(--h);font-weight:var(--hw);font-size:4.2cqw;line-height:1.1;color:var(--brand-text);counter-increment:w}
.tcard{background:var(--surface);border:1px solid var(--line);border-radius:1cqw;padding:2cqw}.tcard b{font-family:var(--h);font-size:2cqw;color:var(--brand-text)}
.tcard p{margin:.6cqw 0}.tcard small{color:var(--muted)}
.do,.dont{margin:0;padding-inline-start:1.5cqw;font-size:1.4cqw;line-height:1.9}.dont li{color:var(--muted)}
.samples{display:grid;grid-template-columns:repeat(4,1fr);gap:1.2cqw;margin-top:2cqw}.sample{background:var(--brand-soft);border-radius:.8cqw;padding:1.2cqw}
.sample small{color:var(--muted)}.sample p{margin:.4cqw 0 0;font-size:1.15cqw}
.clear .zone{position:relative;inline-size:24cqw;padding:6cqw;border:.12cqw dashed var(--accent);background:var(--surface)}
.clear .zone svg{position:relative}.grid{position:absolute;inset:6cqw;background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);background-size:10% 10%}
.sizes{display:flex;align-items:end;gap:2cqw}.sizes figure{margin:0;display:flex;flex-direction:column;align-items:center;gap:.6cqw;font-size:.9cqw;color:var(--muted)}
.bgs{display:grid;grid-template-columns:repeat(4,1fr);gap:1cqw}.bgs div{aspect-ratio:1;display:grid;place-items:center;padding:2cqw;border-radius:.8cqw;border:1px solid var(--line)}
.bad{margin:0;text-align:center;color:var(--muted)}.bad .m{aspect-ratio:1;display:grid;place-items:center;padding:4cqw;background:var(--surface);border-radius:.8cqw;position:relative;overflow:hidden;background-size:4cqw auto}
.bad .m::after{content:"";position:absolute;inset:0;background:linear-gradient(to top right,transparent 49%,#C62828 49.5%,#C62828 50.5%,transparent 51%)}
.bad figcaption{margin-top:.8cqw;font-size:1.1cqw}
.propbar{display:flex;block-size:4cqw;border-radius:.8cqw;overflow:hidden;margin-bottom:2cqw;border:1px solid var(--line)}.propbar i{display:block}
.swatch{border-radius:1cqw;padding:1.6cqw;min-block-size:13cqw;display:flex;flex-direction:column;justify-content:end;gap:.2cqw;font-size:1cqw;border:1px solid var(--line)}
.swatch b{font-size:1.4cqw}.swatch span{font-family:Consolas,monospace;direction:ltr;text-align:end}.small .swatch{min-block-size:8cqw}
.spec{font-family:var(--h);font-weight:var(--hw);font-size:14cqw;line-height:1.1;color:var(--brand-text)}.nums{font-family:var(--b);font-size:3cqw;letter-spacing:.2em;color:var(--muted)}
.icons{display:grid;grid-template-columns:repeat(5,1fr);gap:1.2cqw;margin-top:2cqw}.icon{margin:0;display:flex;flex-direction:column;align-items:center;gap:.5cqw;font-size:.85cqw;color:var(--muted)}
.icon div{inline-size:3cqw;color:var(--ink)}
.browser{border-radius:1cqw;overflow:hidden;border:1px solid var(--line);background:var(--surface);box-shadow:0 2cqw 4cqw -2cqw rgba(0,0,0,.35)}
.browser .bar{display:flex;gap:.5cqw;padding:.8cqw 1cqw;background:var(--raised)}.browser .bar i{inline-size:.8cqw;block-size:.8cqw;border-radius:50%;background:var(--line)}
.s>.browser{inline-size:70cqw;margin:0 auto}.pair{display:grid;grid-template-columns:1fr 1fr;gap:2cqw;align-items:start}
.life{display:grid;grid-template-columns:13cqw 21cqw 1fr;gap:3cqw;align-items:start}
.phone{border:.7cqw solid #111;border-radius:2.2cqw;overflow:hidden;background:#111}.paper{background:#fff;box-shadow:0 1.5cqw 3cqw -1.5cqw rgba(0,0,0,.4);transform:rotate(-2deg)}
.apps{display:grid;grid-template-columns:1fr 1fr;gap:1.2cqw}.app{margin:0}.app img{inline-size:100%;block-size:11cqw;object-fit:contain;background:var(--raised);border-radius:.8cqw}
.app figcaption{font-size:.85cqw;color:var(--muted);margin-top:.3cqw}
.stat b{font-family:var(--h);font-size:9cqw;color:var(--brand);line-height:1}.stat small{font-size:3cqw;color:var(--muted)}
.motifpanel{aspect-ratio:4/3;background-size:6cqw auto;background-color:var(--brand-soft);border-radius:1cqw;display:grid;place-items:center}
.motifpanel .lock{background:var(--bg);padding:2.5cqw 3cqw;border-radius:1cqw;inline-size:60%}
.cmp{background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:1cqw;padding:1.4cqw;font-family:var(--b)}
.cmp b{font-family:var(--h);font-size:1.6cqw;display:block;margin:1cqw 0 .4cqw}.cmp p{font-size:1cqw;color:var(--muted)}
.cmpimg{border-radius:.6cqw;overflow:hidden;border:1px solid var(--line)}.dots{display:flex;gap:.4cqw}.dots i{inline-size:1.6cqw;block-size:1.6cqw;border-radius:50%;border:1px solid var(--line)}
.center{flex:1;display:flex;flex-direction:column;justify-content:center;align-items:flex-start}bdi{font-family:Consolas,monospace}
#nav{position:fixed;inset-block-end:16px;inset-inline-start:16px;background:#000c;color:#fff;font:600 13px/1 Tahoma,sans-serif;padding:8px 12px;border-radius:999px;z-index:2}
@media print{@page{size:1920px 1080px;margin:0}html,body{background:none;block-size:auto;overflow:visible}#nav{display:none}
.s{inline-size:1920px;block-size:1080px;margin:0;break-after:page;print-color-adjust:exact;-webkit-print-color-adjust:exact}}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
"""

JS = """<script>
const S=[...document.querySelectorAll('.s')],nav=document.getElementById('nav');let i=0;
function go(n){i=Math.max(0,Math.min(S.length-1,n));S[i].scrollIntoView({block:'center'});nav.textContent=(i+1)+' / '+S.length}
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting&&e.intersectionRatio>.6){i=S.indexOf(e.target);nav.textContent=(i+1)+' / '+S.length}}),{threshold:[.6]});
S.forEach(s=>io.observe(s));
addEventListener('keydown',e=>{if(['ArrowLeft','ArrowDown','PageDown',' '].includes(e.key)){e.preventDefault();go(i+1)}
else if(['ArrowRight','ArrowUp','PageUp'].includes(e.key)){e.preventDefault();go(i-1)}else if(e.key==='Home')go(0);else if(e.key==='End')go(S.length-1)});
nav.textContent='1 / '+S.length;
</script>"""


def deck(d: Deck) -> str:
    """HTML العرض كاملًا. الخطوط من fonts_base، والصور مسارات نسبية إلى مكان الملف."""
    first = d.chapters[0]
    slides = [cover(d, first), context(d, first), platform(d, first), voice(d, first), idea(d, first)]
    if d.mode == "directions":
        slides.append(construction(d, first))
        for n, ch in enumerate(d.chapters, 1):
            slides += [divider(d, ch, n), system_slide(d, ch), *in_life(d, ch)[:1], *in_life(d, ch)[-1:]]
        if len(d.chapters) > 1:  # اتجاه واحد معتمد خارج الخط: لا مقارنة
            slides.append(compare(d))
    else:
        ch = first
        slides += [construction(d, ch), misuse(d, ch), color(d, ch), typography(d, ch), visual(d, ch), *in_life(d, ch), why(d, ch)]
    slides.append(decision(d, first))
    fonts = {}
    for ch in d.chapters:
        for role, v in ch.fonts.items():
            fonts[f"{ch.direction.id}-{role}"] = v
    return (f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>عرض هوية {esc(d.name_ar)}</title><style>{_faces(fonts, d.fonts_base)}{CSS}</style></head><body>'
            f'{"".join(slides)}<div id="nav" aria-live="polite"></div>{JS}</body></html>')
