"""نظام اللون: تدرجات OKLCH، وأدوار الوضعين الفاتح والداكن، ومصفوفة التباين، ومحاكاة عمى الألوان. دوال نقية حتمية.

OKLab من Björn Ottosson (2020). محاكاة عمى الألوان بمصفوفات Machado وOliveira وFernandes (2009) بشدة 1.0 على sRGB الخطي.
"""
from __future__ import annotations

import math

from ..domain.identity import CheckReport, PalettePolicy
from .contrast import contrast_ratio, hex_to_rgb

STEPS = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)
L_TARGET = (0.97, 0.93, 0.87, 0.79, 0.70, 0.61, 0.52, 0.44, 0.36, 0.28, 0.21)
ROLES = ("paper", "ink", "brand", "accent", "neutral", "success", "warning", "error", "info")
SEMANTIC = ("success", "warning", "error", "info")
SEMANTIC_AR = {"success": "النجاح", "warning": "التنبيه", "error": "الخطأ", "info": "المعلومة"}
CVD = {
    "protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}
CVD_AR = {"protan": "عمى الأحمر", "deutan": "عمى الأخضر", "tritan": "عمى الأزرق"}
DISTINCT = 0.08  # فرق OKLab يُعدّ تمييزًا واضحًا
HUE_EVOLVE = 20.0
TEXT, UI = 4.5, 3.0


# ---------- التحويلات ----------
def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_to_linear(h: str) -> tuple[float, float, float]:
    r, g, b = hex_to_rgb(h)
    return _lin(r / 255), _lin(g / 255), _lin(b / 255)


def linear_to_hex(r: float, g: float, b: float) -> str:
    def ch(v: float) -> int:
        return max(0, min(255, round(_gam(max(0.0, min(1.0, v))) * 255)))
    return f"#{ch(r):02X}{ch(g):02X}{ch(b):02X}"


def linear_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    lm = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    mm = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    sm = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (lm, mm, sm))
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def oklab_to_linear(L: float, a: float, b: float) -> tuple[float, float, float]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    lm, mm, sm = l_ ** 3, m_ ** 3, s_ ** 3
    return (4.0767416621 * lm - 3.3077115913 * mm + 0.2309699292 * sm,
            -1.2684380046 * lm + 2.6097574011 * mm - 0.3413193965 * sm,
            -0.0041960863 * lm - 0.7034186147 * mm + 1.7076147010 * sm)


def hex_to_oklch(h: str) -> tuple[float, float, float]:
    L, a, b = linear_to_oklab(*hex_to_linear(h))
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def _in_gamut(rgb: tuple[float, float, float], eps: float = 1e-6) -> bool:
    return all(-eps <= v <= 1 + eps for v in rgb)


def oklch_to_hex(L: float, C: float, H: float) -> str:
    """يقصّ الإشباع حتى يدخل sRGB مع إبقاء الإضاءة والصبغة."""
    hr = math.radians(H)
    lo, hi = 0.0, C
    rgb = oklab_to_linear(L, C * math.cos(hr), C * math.sin(hr))
    if not _in_gamut(rgb):
        for _ in range(30):
            mid = (lo + hi) / 2
            if _in_gamut(oklab_to_linear(L, mid * math.cos(hr), mid * math.sin(hr))):
                lo = mid
            else:
                hi = mid
        rgb = oklab_to_linear(L, lo * math.cos(hr), lo * math.sin(hr))
    return linear_to_hex(*rgb)


def hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def delta_e(h1: str, h2: str, cvd: str | None = None) -> float:
    def lab(h: str) -> tuple[float, float, float]:
        r, g, b = hex_to_linear(h)
        if cvd:
            m = CVD[cvd]
            r, g, b = (m[0][0] * r + m[0][1] * g + m[0][2] * b, m[1][0] * r + m[1][1] * g + m[1][2] * b,
                       m[2][0] * r + m[2][1] * g + m[2][2] * b)
            r, g, b = (max(0.0, min(1.0, v)) for v in (r, g, b))
        return linear_to_oklab(r, g, b)
    a, b = lab(h1), lab(h2)
    return math.dist(a, b)


# ---------- التدرجات والأدوار ----------
def base_step(base: str) -> int:
    L0 = hex_to_oklch(base)[0]
    return min(zip(STEPS, L_TARGET, strict=True), key=lambda t: abs(t[1] - L0))[0]


def ramp(base: str) -> dict[int, str]:
    """تدرج 50..950 بصبغة اللون الأصلي، والأصلي نفسه في أقرب درجة إضاءة."""
    L0, C0, H0 = hex_to_oklch(base)
    out = {}
    for step, lt in zip(STEPS, L_TARGET, strict=True):
        c = C0 * max(0.12, 1 - (abs(lt - L0) / 0.85) ** 1.4)
        out[step] = oklch_to_hex(lt, c, H0)
    out[base_step(base)] = "#" + base.lstrip("#").upper()
    return out


def lighter_from(step: int) -> tuple[int, ...]:
    """من درجة اللون الأصلي نحو الأفتح: ترتيب البحث في الوضع الداكن."""
    return tuple(s for s in reversed(STEPS) if s <= step)


def darker_from(step: int) -> tuple[int, ...]:
    return tuple(s for s in STEPS if s >= step)


def _first(scale: dict[int, str], order: tuple[int, ...], bg: str, need: float) -> int | None:
    for s in order:
        if contrast_ratio(scale[s], bg) >= need:
            return s
    return None


def mix(base: str, tint: str, t: float) -> str:
    """مزج في OKLab: t من لون tint فوق base. الألوان الخفيفة تُشتق بمزج اللون في الخلفية لا من تدرجه،
    فتبقى من عائلة الورق ولا تنزلق إلى صبغة باهتة مستقلة (العنابي الفاتح يصير ورديًا إن أُخذ من تدرجه)."""
    L1, C1, H1 = hex_to_oklch(base)
    L2, C2, H2 = hex_to_oklch(tint)
    a = (1 - t) * C1 * math.cos(math.radians(H1)) + t * C2 * math.cos(math.radians(H2))
    b = (1 - t) * C1 * math.sin(math.radians(H1)) + t * C2 * math.sin(math.radians(H2))
    return oklch_to_hex((1 - t) * L1 + t * L2, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360)


SOFT_LIGHT, SOFT_DARK = 0.14, 0.24
SOFT_STEP, SOFT_FLOOR = 0.02, 0.04  # تخفيف المزج خطوةً خطوة حين لا يُقرأ اللون على خلفيته الخافتة، وأدناه


def _first_all(scale: dict[int, str], order: tuple[int, ...], bgs: tuple[str, ...], need: float) -> int | None:
    """أول درجة تبلغ الحد على كل الخلفيات: حدود الحقول وحلقة التركيز تقع على السطح كما تقع على الخلفية."""
    return next((s for s in order if all(contrast_ratio(scale[s], bg) >= need for bg in bgs)), None)


def _soft_pair(bg: str, tint: str, fgs: list[str], t0: float, floor: float = SOFT_FLOOR) -> tuple[str, str]:
    """(النص، خلفيته الخافتة): الخلفية مزج tint في bg بالنسبة t0 إن قُرئ النص عليها بحدّ النص، وإلا خُفّف المزج خطوةً خطوة حتى
    floor، ثم جُرّب النص التالي. ما بلغ الحد عند t0 يبقى بقيمته. قرار المالك 2026-11-14: التطبيق المستلم يضع اللون نصًّا على
    خلفيته الخافتة، واتجاه اعتُمد وهذا الزوج فيه 4.45 ردّه اختبار تباين التطبيق."""
    for fg in fgs:
        t = t0
        while t >= floor - 1e-9:
            soft = mix(bg, tint, t)
            if contrast_ratio(fg, soft) >= TEXT:
                return fg, soft
            t -= SOFT_STEP
    return fgs[-1], mix(bg, tint, floor)


def _soft_step(fg: str, candidates: tuple[str, ...]) -> str:
    """خلفية الحالة الخافتة: أول مرشّح يُقرأ عليه لونها بحدّ النص (الأول قيمتها المعتادة)، وإلا أعلاها تباينًا."""
    return next((c for c in candidates if contrast_ratio(fg, c) >= TEXT), max(candidates, key=lambda c: contrast_ratio(fg, c)))


def status_gap(success: str, error: str) -> float:
    """أصغر فرق بين لوني النجاح والخطأ عبر أنواع عمى الألوان الثلاثة (OKLab)."""
    return min(delta_e(success, error, cvd) for cvd in CVD_AR)


def _safe_status(scales: dict, s_order: tuple[int, ...], e_order: tuple[int, ...], bg: str, s0: int, e0: int) -> tuple[int, int]:
    """درجتا النجاح والخطأ: الافتراضيتان إن تمايزتا لعمى الألوان، وإلا أقرب زوج يحقق التباين على الخلفية ويتمايز؛
    وإن لم يوجد فالزوج الأكثر تمايزًا. الإضاءة هي ما يبقى للعين المصابة بعمى الأحمر والأخضر، فالبحث يباعد بينهما بها."""
    s, e = scales["success"], scales["error"]
    if status_gap(s[s0], e[e0]) >= DISTINCT:
        return s0, e0
    ok_s = [x for x in s_order if contrast_ratio(s[x], bg) >= TEXT] or [s0]
    ok_e = [x for x in e_order if contrast_ratio(e[x], bg) >= TEXT] or [e0]
    pairs = sorted(((a, b) for a in ok_s for b in ok_e), key=lambda t: abs(STEPS.index(t[0]) - STEPS.index(s0)) + abs(STEPS.index(t[1]) - STEPS.index(e0)))
    good = [t for t in pairs if status_gap(s[t[0]], e[t[1]]) >= DISTINCT]
    return good[0] if good else max(pairs, key=lambda t: status_gap(s[t[0]], e[t[1]]))


def build_system(colors: dict[str, str]) -> dict:
    """يعيد scales وroles (light وdark) لكل دور؛ الأدوار قيم hex جاهزة للـtokens."""
    scales = {k: ramp(colors[k]) for k in ("brand", "accent", "neutral", *SEMANTIC)}
    base = {k: base_step(colors[k]) for k in scales}
    n = scales["neutral"]
    up = {k: lighter_from(base[k]) for k in scales}
    down = {k: darker_from(base[k]) for k in scales}
    paper, ink = colors["paper"].upper(), colors["ink"].upper()
    on_brand = "#FFFFFF" if contrast_ratio("#FFFFFF", colors["brand"]) >= contrast_ratio(ink, colors["brand"]) else ink
    surface = n[50] if n[50].upper() != paper else n[100]
    # النص الثانوي يقع على الأسطح الثلاثة لا على الخلفية وحدها (قرار المالك 2026-11-15 بعد قياس منصة المدرسة: 4.26 على raised)
    muted = n[_first_all(n, (600, 700, 800, 900), (paper, surface, n[100]), TEXT) or 900]
    light = {
        "bg": paper, "surface": surface, "raised": n[100], "border": n[200],
        "text": ink, "text_muted": muted, "brand": colors["brand"].upper(), "brand_strong": scales["brand"][down["brand"][1] if len(down["brand"]) > 1 else 950],
        "on_brand": on_brand, "accent": colors["accent"].upper(),
    }
    faces = (paper, light["surface"])
    light["border_strong"] = n[_first_all(n, (400, 500, 600, 700), faces, UI) or 700]
    light["focus"] = scales["info"][_first_all(scales["info"], (600, 700, 800, 900), faces, UI) or 900]
    # نص العلامة ورابطها (قرار المالك 2026-11-18 على «مرصد»: الفيروزي #089770 للشعار 3.22:1 ودون حدّ النص): لون العلامة نفسه إن
    # بلغ حدّ النص على الورق، وإلا أقرب درجة أغمق من مقياسه تبلغه؛ فالاتجاه الذي يبلغه لونه لا يتغيّر فيه شيء
    b = scales["brand"]
    texts = [light["brand"]] if contrast_ratio(light["brand"], paper) >= TEXT else (
        [b[x] for x in down["brand"] if contrast_ratio(b[x], paper) >= TEXT] or [b[950]])
    light["brand_text"], light["brand_soft"] = _soft_pair(paper, colors["brand"], texts, SOFT_LIGHT)
    a = scales["accent"]
    light["accent_text"], light["accent_soft"] = _soft_pair(
        paper, colors["accent"], [a[x] for x in down["accent"] if contrast_ratio(a[x], paper) >= TEXT] or [a[950]], SOFT_LIGHT * 1.6, SOFT_LIGHT * 0.8)
    for k in SEMANTIC:
        s = scales[k]
        light[k] = s[_first(s, down[k], paper, TEXT) or 950]
    ls, le = _safe_status(scales, down["success"], down["error"], paper, _first(scales["success"], down["success"], paper, TEXT) or 950,
                          _first(scales["error"], down["error"], paper, TEXT) or 950)
    light["success"], light["error"] = scales["success"][ls], scales["error"][le]
    for k in SEMANTIC:  # بعد تثبيت لونَي النجاح والخطأ: الخلفية الخافتة تتبع النص لا العكس
        s50 = scales[k][50]
        light[f"{k}_soft"] = _soft_step(light[k], (s50, mix(s50, "#FFFFFF", 0.5), "#FFFFFF"))
    dbg = n[950]
    dfaces = (dbg, n[900])
    dark = {
        "bg": dbg, "surface": n[900], "raised": n[800], "border": n[700],
        "border_strong": n[_first_all(n, (600, 500, 400, 300), dfaces, UI) or 300],
        "text": n[50], "text_muted": n[_first_all(n, (300, 200, 100), (dbg, n[900], n[800]), TEXT) or 100],
        "brand": scales["brand"][_first(scales["brand"], up["brand"], dbg, TEXT) or 50],
        "accent": scales["accent"][_first(scales["accent"], up["accent"], dbg, UI) or 50],
        "focus": scales["info"][_first_all(scales["info"], up["info"], dfaces, UI) or 50],
    }
    dark["brand_soft"] = _soft_pair(dbg, dark["brand"], [dark["brand"]], SOFT_DARK)[1]
    dark["brand_text"] = dark["brand"]  # درجة ليل العلامة تُختار بحدّ النص أصلًا
    dark["accent_text"], dark["accent_soft"] = _soft_pair(
        dbg, dark["accent"], [a[x] for x in up["accent"] if contrast_ratio(a[x], dbg) >= TEXT] or [a[50]], SOFT_DARK, SOFT_DARK / 2)
    db = next(s for s in STEPS if scales["brand"][s] == dark["brand"])
    dark["brand_strong"] = scales["brand"][max([s for s in STEPS if s < db] or [50])]
    dark["on_brand"] = dbg if contrast_ratio(dbg, dark["brand"]) >= contrast_ratio("#FFFFFF", dark["brand"]) else "#FFFFFF"
    for k in SEMANTIC:
        s = scales[k]
        dark[k] = s[_first(s, up[k], dbg, TEXT) or 50]
    ds, de = _safe_status(scales, up["success"], up["error"], dbg, _first(scales["success"], up["success"], dbg, TEXT) or 50,
                          _first(scales["error"], up["error"], dbg, TEXT) or 50)
    dark["success"], dark["error"] = scales["success"][ds], scales["error"][de]
    for k in SEMANTIC:
        s900, s950 = scales[k][900], scales[k][950]
        dark[f"{k}_soft"] = _soft_step(dark[k], (s900, s950, mix(s950, "#000000", 0.5), "#000000"))
    return {"scales": scales, "light": light, "dark": dark}



def with_night(system: dict, night_colors: dict[str, str]) -> dict:
    """نظام الاتجاه بليل اتجاه آخر (قرار المالك 2026-11-17 على «مسك»): النهار والمقاييس كما هي، وأدوار الليل كلها من
    ألوان ذلك الاتجاه بالاشتقاق نفسه، فتبقى قيم ليله المعتمد حرفًا بحرف."""
    return {**system, "dark": build_system(night_colors)["dark"]}


# ---------- الفحوص ----------
TEXT_PAIRS = (("text", "bg", "النص على الخلفية"), ("text", "surface", "النص على السطح"), ("text_muted", "bg", "النص الثانوي"), ("text_muted", "raised", "النص الثانوي على السطح المرفوع"),
              ("brand_text", "bg", "لون العلامة نصًا أو رابطًا"), ("on_brand", "brand", "النص على لون العلامة"),
              *((k, "bg", f"نص {SEMANTIC_AR[k]}") for k in SEMANTIC))
SOFT_PAIRS = (("brand_text", "brand_soft", "لون العلامة"), ("accent_text", "accent_soft", "نص التمييز"),
              *((k, f"{k}_soft", SEMANTIC_AR[k]) for k in SEMANTIC))


def check_system(colors: dict[str, str], system: dict, *, accent_informational: bool,
                 policy: PalettePolicy, brief_palette: dict[str, str]) -> CheckReport:
    rep = CheckReport()
    for mode, mode_ar in (("light", "فاتح"), ("dark", "داكن")):
        roles = system[mode]
        for fg, bg, label in TEXT_PAIRS:
            r = contrast_ratio(roles[fg], roles[bg])
            rep.add(f"تباين {label} ({mode_ar})", r >= TEXT, f"{r}:1 (الحد {TEXT})")
        r = contrast_ratio(roles["accent"], roles["bg"])
        rep.add(f"تباين التمييز ({mode_ar})", r >= UI or not accent_informational,
                f"{r}:1 — {'معلوماتي يلزمه 3' if accent_informational else 'زخرفي معفى'}", blocking=accent_informational)
        r = contrast_ratio(roles["border_strong"], roles["bg"])
        rep.add(f"تباين حدود الحقول ({mode_ar})", r >= UI, f"{r}:1 (الحد {UI})")
        # اللون نصًّا على خلفيته الخافتة (شارة، تنبيه، صف محدَّد): الزوج الذي لم يُقَس فاعتُمد اتجاه «أوراق» v6 وهو فيه دون الحد
        for fg, bg, label in SOFT_PAIRS:
            if fg in roles and bg in roles:
                r = contrast_ratio(roles[fg], roles[bg])
                rep.add(f"تباين {label} على خلفيته الخافتة ({mode_ar})", r >= TEXT, f"{r}:1 (الحد {TEXT})")
        for role, label in (("border_strong", "حدود الحقول"), ("focus", "حلقة التركيز")):
            r = contrast_ratio(roles[role], roles["surface"])
            rep.add(f"تباين {label} على السطح ({mode_ar})", r >= UI, f"{r}:1 (الحد {UI})")
        r = contrast_ratio(roles["focus"], roles["bg"])
        rep.add(f"تباين حلقة التركيز ({mode_ar})", r >= UI, f"{r}:1 (الحد {UI})")
    for cvd, ar in CVD_AR.items():
        d = delta_e(colors["brand"], colors["accent"], cvd)
        rep.add(f"العلامة والتمييز مع {ar}", d >= DISTINCT or not accent_informational, f"فرق {d:.3f} (الحد {DISTINCT})",
                blocking=accent_informational)
        for mode, mode_ar in (("light", "فاتح"), ("dark", "داكن")):
            d2 = delta_e(system[mode]["success"], system[mode]["error"], cvd)
            rep.add(f"النجاح والخطأ مع {ar} ({mode_ar})", d2 >= DISTINCT, f"فرق {d2:.3f} (الحد {DISTINCT})؛ ويرافقهما رمز أو نص دائمًا",
                    blocking=False)
    if policy is PalettePolicy.RESPECT:
        for k in ("paper", "ink", "brand", "accent"):
            same = colors[k].upper() == str(brief_palette.get(k, "")).upper()
            rep.add(f"احترام لون {k} في الموجز", same, f"{colors[k]} مقابل {brief_palette.get(k)}")
    elif policy is PalettePolicy.EVOLVE:
        for k in ("brand", "accent"):
            if not brief_palette.get(k):
                continue
            d = hue_distance(hex_to_oklch(colors[k])[2], hex_to_oklch(str(brief_palette[k]))[2])
            rep.add(f"تطوير {k} بإبقاء الطابع", d <= HUE_EVOLVE, f"فرق الصبغة {d:.1f}° (الحد {HUE_EVOLVE:g}°)")
    return rep
