"""صفحتا الهوية: لوحة الاتجاهات الثلاثة للقرار، ودليل الهوية الكامل (HTML يُطبع PDF). عربية RTL بخطوط الهوية نفسها."""
from __future__ import annotations

from xml.sax.saxutils import escape as _esc

from ..domain.identity import CheckReport, Direction, Strategy
from .color_system import SEMANTIC_AR, STEPS
from .contrast import contrast_ratio
from .design_tokens import face_weight
from .type_system import SCALE_AR, type_scale

ROLE_AR = {"bg": "الخلفية", "surface": "السطح", "raised": "السطح المرفوع", "border": "الحد", "border_strong": "حد الحقول",
           "text": "النص", "text_muted": "النص الثانوي", "brand": "العلامة", "brand_strong": "العلامة القوية", "brand_text": "نص العلامة",
           "brand_soft": "العلامة الخفيفة", "on_brand": "النص على العلامة", "accent": "التمييز", "accent_soft": "التمييز الخفيف",
           "focus": "إطار التركيز", **SEMANTIC_AR, **{f"{k}_soft": f"خلفية {v}" for k, v in SEMANTIC_AR.items()}}
SCALE_NAME_AR = {"brand": "العلامة", "accent": "التمييز", "neutral": "المحايد", **SEMANTIC_AR}


def esc(s: object) -> str:
    return _esc(str(s), {'"': "&quot;"})


def _faces(fonts: dict[str, dict], base: str) -> str:
    seen, out = set(), []
    for role, v in fonts.items():
        if v["file"] in seen:
            continue
        seen.add(v["file"])
        out.append(f'@font-face{{font-family:"{v["family"]}";src:url("{base}{v["file"]}") format("truetype");'
                   f'font-weight:{face_weight(fonts, role)};font-display:swap}}')
    return "".join(out)


def _css(r: dict, fonts: dict[str, dict], base: str) -> str:
    h, b = fonts["heading"], fonts["body"]
    return _faces(fonts, base) + f"""
:root{{--bg:{r["bg"]};--surface:{r["surface"]};--raised:{r["raised"]};--line:{r["border"]};--ink:{r["text"]};--muted:{r["text_muted"]};
--brand:{r["brand"]};--brand-strong:{r["brand_strong"]};--brand-soft:{r["brand_soft"]};--brand-text:{r.get("brand_text", r["brand"])};--on-brand:{r["on_brand"]};--accent:{r["accent"]};
--h:"{h["family"]}",Tahoma,sans-serif;--b:"{b["family"]}",Tahoma,sans-serif}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}body{{margin:0;color:var(--ink);font:{b["weight"]} 16px/1.7 var(--b);background:var(--bg)}}
h1,h2,h3{{font-family:var(--h);font-weight:{h["weight"]};line-height:1.3;margin:0 0 .5em;color:var(--ink)}}
h1{{font-size:3rem}}h2{{font-size:1.95rem}}h3{{font-size:1.25rem}}
p{{margin:0 0 .8em;max-inline-size:68ch}}.muted{{color:var(--muted)}}
.wrap{{max-inline-size:1180px;margin-inline:auto;padding:48px 32px}}
section{{border-block-start:1px solid var(--line);padding-block:40px}}
.kick{{display:inline-block;font-size:.8rem;letter-spacing:0;color:var(--brand-text);font-weight:700;margin-block-end:.4em}}
.grid{{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(var(--min,220px),1fr))}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px}}
.sw{{display:flex;flex-direction:column;border-radius:10px;overflow:hidden;border:1px solid var(--line);background:var(--surface)}}
.sw i{{display:block;block-size:72px}}.sw span{{padding:8px 10px;font-size:.85rem;line-height:1.5}}
.sw code,code,pre{{font-family:Consolas,"Cascadia Mono",monospace;direction:ltr;unicode-bidi:isolate}}
.ramp{{display:grid;grid-template-columns:repeat({len(STEPS)},1fr);border-radius:10px;overflow:hidden;margin-block:6px 18px}}
.ramp i{{block-size:44px;display:flex;align-items:end;justify-content:center;font:600 .62rem/1.6 Consolas,monospace;padding-bottom:2px}}
table{{border-collapse:collapse;inline-size:100%;font-size:.9rem}}th,td{{padding:8px;border-block-end:1px solid var(--line);text-align:start;vertical-align:middle}}
th{{color:var(--muted);font-weight:400}}.ok{{color:{r["success"]}}}.no{{color:{r["error"]}}}
.chip{{display:inline-block;inline-size:18px;block-size:18px;border-radius:4px;border:1px solid var(--line);vertical-align:-4px;margin-inline-end:6px}}
.figure{{background:var(--raised);border-radius:12px;padding:16px;display:grid;place-items:center}}
.figure img{{max-inline-size:100%;block-size:auto;display:block}}
.figure.dark{{background:{r["brand"]}}}
pre{{background:var(--raised);border-radius:10px;padding:14px;overflow:auto;font-size:.8rem;line-height:1.6}}
.icons{{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:12px}}
.icons div{{display:flex;flex-direction:column;align-items:center;gap:8px;padding:14px 6px;border:1px solid var(--line);border-radius:10px;background:var(--surface);font-size:.8rem;color:var(--muted)}}
.icons svg{{inline-size:32px;block-size:32px;color:var(--ink)}}
.cover{{min-block-size:88vh;display:grid;align-content:center;gap:28px}}
.cover .lock{{max-inline-size:620px}}.band{{block-size:120px;border-radius:12px}}
@page{{size:A4;margin:14mm}}
@media print{{.wrap{{padding:0}}section{{break-before:page;border:0}}.cover{{min-block-size:auto}}a{{color:inherit;text-decoration:none}}}}
"""


def _checks(rep: CheckReport) -> str:
    rows = "".join(f'<tr><td class="{"ok" if c.ok else "no"}">{"✓" if c.ok else ("✗" if c.blocking else "!")}</td>'
                   f'<td>{esc(c.name)}</td><td class="muted">{esc(c.detail)}</td></tr>' for c in rep.checks)
    return f"<table><tbody>{rows}</tbody></table>"


def _ramps(system: dict) -> str:
    out = []
    for name, sc in system["scales"].items():
        cells = "".join(f'<i style="background:{v};color:{"#000" if contrast_ratio("#000000", v) > contrast_ratio("#FFFFFF", v) else "#fff"}" '
                        f'title="{name}-{s} {v}">{s}</i>' for s, v in sc.items())
        out.append(f'<h3>{esc(SCALE_NAME_AR.get(name, name))}</h3><div class="ramp">{cells}</div>')
    return "".join(out)


def _roles(system: dict) -> str:
    rows = []
    for k in system["light"]:
        lv, dv = system["light"][k], system["dark"][k]
        rows.append(f'<tr><td>{esc(ROLE_AR.get(k, k))}</td><td><code>--{k.replace("_", "-")}</code></td>'
                    f'<td><span class="chip" style="background:{lv}"></span><code>{lv}</code></td>'
                    f'<td><span class="chip" style="background:{dv}"></span><code>{dv}</code></td></tr>')
    return f'<table><thead><tr><th>الدور</th><th>المتغير</th><th>فاتح</th><th>داكن</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'


def _rest_of_system(system: dict) -> str:
    """ألوان الحالات في الوضع الفاتح، ثم الأدوار نفسها في الوضع الداكن على خلفيته."""
    light, dark = system["light"], system["dark"]
    status = "".join(f'<div class="sw"><i style="background:{light[k]}"></i><span>{esc(ROLE_AR[k])}<br><code>{light[k]}</code></span></div>'
                     for k in ("text_muted", "success", "warning", "error", "info"))
    chips = "".join(f'<div class="sw" style="background:{dark["surface"]};border-color:{dark["border"]};color:{dark["text"]}">'
                    f'<i style="background:{dark[k]}"></i><span>{esc(ROLE_AR[k])}<br><code>{dark[k]}</code></span></div>'
                    for k in ("brand", "accent", "text", "success", "warning", "error", "info"))
    return (f'{status}</div><h3 style="margin-top:18px">الوضع الداكن (مشتق آليًا)</h3>'
            f'<div class="grid" style="--min:96px;background:{dark["bg"]};padding:12px;border-radius:10px">{chips}')


def directions_board(name_ar: str, version: int, key: str, strategy: Strategy, boards: list[dict], fonts_base: str) -> str:
    """boards: [{direction, system, fonts, checks, apps: [(title, svg_path)], motif_band}]؛ الصفحة للقرار لا للنشر."""
    all_fonts: dict[str, dict] = {}
    for b in boards:
        for r, v in b["fonts"].items():
            all_fonts[f'{b["direction"].id}-{r}'] = v
    first = boards[0]["system"]["light"]
    cols = []
    for b in boards:
        d: Direction = b["direction"]
        r, f = b["system"]["light"], b["fonts"]
        sw = "".join(f'<div class="sw"><i style="background:{r[k]}"></i><span>{esc(ROLE_AR[k])}<br><code>{r[k]}</code></span></div>'
                     for k in ("brand", "accent", "bg", "text", "brand_soft"))
        if len(boards) == 1:  # اتجاه معتمد خارج الخط: يرى المالك ما أُكمل بعد اختياره (ألوان الحالات والوضع الداكن المشتق)
            sw += _rest_of_system(b["system"])
        apps = "".join(f'<figure class="figure" style="margin:0 0 10px"><img src="{esc(p)}" alt="{esc(t)}"></figure>' for t, p in b["apps"])
        status = "يجتاز الفحوص" if b["checks"].ok else "لا يجتاز الفحوص بعد"
        cols.append(f"""<article class="card" style="--min:300px">
<span class="kick">{esc(d.id)} · {status}</span>
<h2 style="font-family:'{f["heading"]["family"]}';font-weight:{f["heading"]["weight"]}">{esc(d.name)}</h2>
<p class="muted">{esc(d.idea)}</p>
<div class="grid" style="--min:96px">{sw}</div>
<h3 style="margin-top:18px">الطباعة</h3>
<p style="font-family:'{f["heading"]["family"]}';font-weight:{f["heading"]["weight"]};font-size:1.9rem;line-height:1.3;margin:0">{esc(name_ar)}</p>
<p style="font-family:'{f["body"]["family"]}';font-weight:{f["body"]["weight"]}">{esc(strategy.positioning)}</p>
<p class="muted" style="font-size:.85rem">{esc(f["heading"]["family"])} {f["heading"]["weight"]} للعناوين، و{esc(f["body"]["family"])} {f["body"]["weight"]} للنص، والأرقام {"هندية" if d.numerals == "arab" else "عربية"}.</p>
<h3>اللغة البصرية</h3><div class="band" style="background-image:url('{esc(b["motif_band"])}');background-size:auto 100%"></div>
<p class="muted" style="font-size:.85rem;margin-top:6px">{esc(d.motif_rule)}</p>
<h3>مطبّقًا</h3>{apps}
<details><summary>الفحوص ({sum(c.ok for c in b["checks"].checks)} من {len(b["checks"].checks)})</summary>{_checks(b["checks"])}</details>
</article>""")
    return f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>اتجاهات الهوية · {esc(name_ar)}</title><style>{_css(first, {"heading": boards[0]["fonts"]["heading"], "body": boards[0]["fonts"]["body"]}, fonts_base)}
{_faces(all_fonts, fonts_base)}</style></head><body><div class="wrap">
<span class="kick">سِمة · v{version} · {esc(key)}</span><h1>{"ثلاثة اتجاهات لهوية" if len(boards) > 1 else "الاتجاه المعتمد لهوية"} «{esc(name_ar)}»</h1>
<p class="muted">{"كل اتجاه نظام كامل: لون وطباعة ولغة بصرية، مطبّقًا على تطبيقين حقيقيين. اختر واحدًا من صفحة «اليوم» في منصة سِمة، أو اطلب تعديلًا بسبب." if len(boards) > 1 else "الاتجاه الذي اخترته مكتملًا نظامًا: ألوانه كلها وتدرجاتها ووضعه الداكن المشتق وطباعته ونمطه، مطبّقًا على تطبيقين حقيقيين. اعتمده من صفحة «اليوم» في منصة سِمة، أو اطلب تعديلًا بسبب."}</p>
<div class="grid" style="--min:340px;align-items:start">{"".join(cols)}</div></div></body></html>"""


def brand_book(ctx: dict) -> str:
    """ctx: name_ar, slug, version, key, strategy, direction, system, fonts, checks, mark_files, apps, icons, motif, tokens_css, imagery."""
    s: Strategy = ctx["strategy"]
    d: Direction = ctx["direction"]
    sysm, fonts, r = ctx["system"], ctx["fonts"], ctx["system"]["light"]
    traits = "".join(f'<div class="card"><h3>{esc(t.trait)}</h3><p>{esc(t.means)}</p><p class="muted">ليس: {esc(t.not_)}</p></div>'
                     for t in s.personality)
    do = "".join(f"<li>{esc(x)}</li>" for x in s.voice_do)
    dont = "".join(f"<li>{esc(x)}</li>" for x in s.voice_dont)
    samples = "".join(f'<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>' for k, v in
                      zip(("عنوان", "زر", "رسالة خطأ", "حالة فارغة"), s.samples.values(), strict=True))
    marks = "".join(f'<figure class="figure{" dark" if dark else ""}" style="margin:0"><img src="../{esc(f)}" alt="{esc(t)}" style="max-block-size:160px"></figure>'
                    f'<p class="muted" style="font-size:.85rem;margin:.4em 0 1em">{esc(t)} · <code>{esc(f)}</code></p>' for f, t, dark in ctx["mark_files"])
    scale = "".join(f'<tr><td>{esc(SCALE_AR[k])}</td><td><code>{v["px"]}px · {v["rem"]}rem · {v["line"]}</code></td>'
                    f'<td style="font-family:var({"--h" if v["line"] < 1.5 else "--b"});font-size:{v["px"]}px;line-height:{v["line"]}">{esc(ctx["name_ar"])}</td></tr>'
                    for k, v in type_scale().items())
    apps = "".join(f'<figure class="figure" style="margin:0"><img src="{esc(p)}" alt="{esc(t)}"></figure>'
                   f'<p class="muted" style="font-size:.85rem;margin:.4em 0 1.2em">{esc(t)}</p>' for t, p in ctx["apps"])
    icons = "".join(f'<div>{i["svg"]}<span>{esc(i["subject"])}</span></div>' for i in ctx["icons"])
    files = "".join(f"<li><code>{esc(f)}</code></li>" for f in ctx["files"])
    return f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>دليل هوية {esc(ctx["name_ar"])}</title><style>{_css(r, fonts, "fonts/")}</style></head><body><div class="wrap">
<header class="cover"><img class="lock" src="../{esc(ctx["lockup_file"])}" alt="شعار {esc(ctx["name_ar"])}">
<div><span class="kick">دليل الهوية · الإصدار {ctx["version"]} · <code>{esc(ctx["key"])}</code></span>
<h1>{esc(ctx["name_ar"])}</h1><p style="font-size:1.4rem;font-family:var(--h)">{esc(s.tagline)}</p></div>
<div class="band" style="background-image:url('patterns/motif-soft.svg');background-size:auto 100%"></div></header>

<section><span class="kick">١ · المنصة</span><h2>من نحن ولمن</h2><p style="font-size:1.25rem">{esc(s.positioning)}</p>
<p><strong>الوعد:</strong> {esc(s.promise)}</p><div class="grid">{traits}</div>
<h3 style="margin-top:24px">نبرة الصوت</h3><div class="grid"><div class="card"><h3>نقول</h3><ul>{do}</ul></div><div class="card"><h3>لا نقول</h3><ul>{dont}</ul></div></div>
<table style="margin-top:16px"><tbody>{samples}</tbody></table>
{f'<h3 style="margin-top:24px">اتجاه الصورة</h3><p>{esc(s.imagery)}</p>' if s.imagery else ""}</section>

<section><span class="kick">٢ · العلامة</span><h2>الرمز والكلمة</h2><p>{esc(ctx["concept"])}</p>
<p class="muted">مساحة خالية حول الرمز لا تقل عن ربع عرضه. الحد الأدنى 16 بكسل للرمز و24 بكسل ارتفاعًا للقفل. لا تدوير ولا تمديد ولا ظل ولا تدرج ولا تغيير نسب.</p>
<div class="grid" style="--min:260px">{marks}</div></section>

<section><span class="kick">٣ · اللون</span><h2>{esc(d.name)}</h2><p>{esc(d.idea)}</p>{_ramps(sysm)}
<h3>الأدوار في الوضعين</h3><p class="muted">الواجهة تستعمل الأدوار لا القيم الخام؛ الوضع الداكن مشتق آليًا بأول درجة تبلغ التباين.</p>{_roles(sysm)}
<h3 style="margin-top:24px">الفحوص</h3>{_checks(ctx["checks"])}</section>

<section><span class="kick">٤ · الطباعة</span><h2>خطّان وسلّم واحد</h2>
<p>العناوين بخط <strong>{esc(fonts["heading"]["family"])}</strong> بوزن {fonts["heading"]["weight"]}، والنص بخط <strong>{esc(fonts["body"]["family"])}</strong> بوزن {fonts["body"]["weight"]}.
الأرقام {"الهندية (٠١٢٣)" if d.numerals == "arab" else "العربية (0123)"}. ارتفاع السطر 1.7 للنص العربي و1.3 للعناوين، ولا نص تحت 12 بكسل. الخطوط بترخيص OFL ومرفقة في <code>fonts/</code>.</p>
<table><tbody>{scale}</tbody></table></section>

<section><span class="kick">٥ · اللغة البصرية</span><h2>النمط</h2><p>{esc(d.motif_rule)}</p>
<div class="grid" style="--min:280px"><div class="band" style="background-image:url('patterns/motif-soft.svg');background-size:auto 100%"></div>
<div class="band" style="background:{r["brand"]};background-image:url('patterns/motif-strong.svg');background-size:auto 100%"></div></div>
<p class="muted" style="margin-top:10px">النمط خلفية لا بطل: لا يجاور الشعار مباشرة، ولا يحمل نصًا فوقه إلا على سطح مصمت.</p></section>

{f'<section><span class="kick">٦ · الأيقونات</span><h2>مجموعة الأيقونات</h2><p class="muted">شبكة 24، خط واحد بسماكة موحّدة، بلون النص (currentColor).</p><div class="icons">{icons}</div></section>' if icons else ""}

{f'<section><span class="kick">٧ · التطبيقات</span><h2>الهوية في الاستعمال</h2><div class="grid" style="--min:420px">{apps}</div></section>' if apps else ""}

{'<section><span class="kick">٨ · الحركة</span><h2>ظهور الرمز</h2><p>حركة قصيرة 600 مللي ثانية بتتابع العناصر، وتُلغى عند تفضيل تقليل الحركة. افتح <code>motion/mark-intro.html</code>.</p></section>' if ctx.get("motion") else ""}

<section><span class="kick">٩ · الملفات</span><h2>tokens والملفات</h2><p>الصيغ: CSS بالوضعين، وSCSS، وJSON بمعيار DTCG (لـFigma عبر Tokens Studio)، وpreset لـTailwind.</p>
<pre>{esc(ctx["tokens_css"][:1600])}…</pre><ul>{files}</ul></section>
</div></body></html>"""
