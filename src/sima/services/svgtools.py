"""أدوات SVG حتمية: تحليل، فحص ثابت، اشتقاق الصيغ (أحادية، معكوسة، ممرآة، مشوّشة)، إعادة التلوين."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

_FORBIDDEN_TAGS = {
    "text": "نص حي <text> (يجب تحويله إلى مسارات)",
    "tspan": "نص حي <tspan>",
    "linearGradient": "تدرج خطي",
    "radialGradient": "تدرج شعاعي",
    "filter": "فلتر",
    "image": "صورة نقطية مدمجة",
    "foreignObject": "عنصر أجنبي",
    "script": "سكربت",
    "style": "ورقة أنماط داخلية (استعمل سمات مباشرة)",
}
_COLOR_ATTRS = ("fill", "stroke", "stop-color", "color")
_HEX_RE = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?")


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def parse(svg: str) -> ET.Element:
    return ET.fromstring(svg.encode("utf-8") if isinstance(svg, str) else svg)


def to_string(root: ET.Element) -> str:
    return ET.tostring(root, encoding="unicode")


def view_box(root: ET.Element) -> tuple[float, float, float, float] | None:
    vb = root.get("viewBox")
    if not vb:
        return None
    nums = [float(x) for x in _NUM_RE.findall(vb)]
    if len(nums) != 4:
        return None
    return nums[0], nums[1], nums[2], nums[3]


def normalize_hex(c: str) -> str:
    h = c.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return "#" + h.upper()


def _style_colors(style: str) -> list[str]:
    out = []
    for prop in style.split(";"):
        if ":" not in prop:
            continue
        k, v = prop.split(":", 1)
        if k.strip() in _COLOR_ATTRS:
            out.append(v.strip())
    return out


def colors_used(root: ET.Element) -> set[str]:
    found: set[str] = set()
    for el in root.iter():
        vals = [el.get(a) for a in _COLOR_ATTRS] + _style_colors(el.get("style", ""))
        for v in vals:
            if not v:
                continue
            v = v.strip().lower()
            if v in ("none", "transparent", "currentcolor", "inherit"):
                continue
            m = _HEX_RE.match(v)
            if m:
                found.add(normalize_hex(v))
            elif v == "black":
                found.add("#000000")
            elif v == "white":
                found.add("#FFFFFF")
            else:
                found.add(v)
    return found


@dataclass
class StaticReport:
    ok: bool
    findings: list[str] = field(default_factory=list)
    colors: set[str] = field(default_factory=set)
    shapes: int = 0
    anchors: int = 0
    view_box: tuple[float, float, float, float] | None = None


def count_anchors(root: ET.Element) -> int:
    n = 0
    for el in root.iter():
        t = _local(el.tag)
        if t == "path":
            n += len(re.findall(r"[MLHVCSQTAZmlhvcsqtaz]", el.get("d", "")))
        elif t in ("rect", "circle", "ellipse", "line"):
            n += 4 if t == "rect" else 2
        elif t in ("polygon", "polyline"):
            n += len(_NUM_RE.findall(el.get("points", ""))) // 2
    return n


def count_shapes(root: ET.Element) -> int:
    return sum(1 for el in root.iter() if _local(el.tag) in ("path", "rect", "circle", "ellipse", "polygon", "polyline", "line"))


def static_audit(svg: str, *, allowed_colors: set[str] | None = None, max_colors: int = 3) -> StaticReport:
    """لا نص حي، لا تدرجات، لا فلاتر، لا صور؛ viewBox موجود؛ عدد الألوان محدود."""
    try:
        root = parse(svg)
    except ET.ParseError as exc:
        return StaticReport(ok=False, findings=[f"SVG غير صالح: {exc}"])
    findings: list[str] = []
    for el in root.iter():
        t = _local(el.tag)
        if t in _FORBIDDEN_TAGS:
            findings.append(f"ممنوع: {_FORBIDDEN_TAGS[t]}")
        if el.get("filter") or "filter:" in el.get("style", ""):
            findings.append("ممنوع: فلتر على عنصر")
        if el.get("opacity") not in (None, "1") or (el.get("fill-opacity") not in (None, "1")) or (el.get("stroke-opacity") not in (None, "1")):
            findings.append("شفافية جزئية؛ العلامة الأساسية تُبنى بألوان مصمتة")
    vb = view_box(root)
    if vb is None:
        findings.append("لا viewBox")
    cols = colors_used(root)
    if allowed_colors is not None:
        bad = sorted(c for c in cols if c not in allowed_colors)
        if bad:
            findings.append("ألوان خارج المسموح في هذه المرحلة: " + ", ".join(bad))
    if len(cols) > max_colors:
        findings.append(f"عدد الألوان {len(cols)} يتجاوز الحد {max_colors}")
    shapes, anchors = count_shapes(root), count_anchors(root)
    if shapes == 0:
        findings.append("لا أشكال مرسومة")
    uniq = list(dict.fromkeys(findings))
    return StaticReport(ok=not uniq, findings=uniq, colors=cols, shapes=shapes, anchors=anchors, view_box=vb)


def _recolor_value(v: str | None, mapping: dict[str, str], default: str | None) -> str | None:
    if v is None:
        return None
    lv = v.strip().lower()
    if lv in ("none", "transparent"):
        return v
    key = normalize_hex(lv) if _HEX_RE.match(lv) else {"black": "#000000", "white": "#FFFFFF"}.get(lv, lv)
    if key in mapping:
        return mapping[key]
    return default if default is not None else v


def recolor(svg: str, mapping: dict[str, str], default: str | None = None, *, keep_background: bool = True) -> str:
    """يعيد تلوين fill/stroke حسب الخريطة (مفاتيح hex كبيرة)؛ default لما لم يُذكر.

    العنصر الموسوم data-role="background" يُترك إن keep_background.
    """
    root = parse(svg)
    norm = {normalize_hex(k): v for k, v in mapping.items()}
    for el in root.iter():
        if keep_background and el.get("data-role") == "background":
            continue
        for attr in ("fill", "stroke"):
            if el.get(attr) is not None:
                nv = _recolor_value(el.get(attr), norm, default)
                if nv is not None:
                    el.set(attr, nv)
        style = el.get("style")
        if style:
            parts = []
            for prop in style.split(";"):
                if ":" in prop:
                    k, v = prop.split(":", 1)
                    if k.strip() in ("fill", "stroke"):
                        v = _recolor_value(v, norm, default) or v
                    parts.append(f"{k.strip()}:{v.strip()}")
            el.set("style", ";".join(parts))
    return to_string(root)


def mono(svg: str, ink: str = "#000000") -> str:
    """كل ما ليس none يصبح لون الحبر الواحد، وتُحذف الخلفية."""
    s = strip_background(svg)
    return recolor(s, {}, default=ink, keep_background=False)


def reversed_(svg: str, ink: str = "#FFFFFF", background: str = "#000000") -> str:
    """نسخة معكوسة: حبر فاتح على خلفية داكنة تملأ viewBox."""
    m = mono(svg, ink)
    return with_background(m, background)


def strip_background(svg: str) -> str:
    root = parse(svg)
    for parent in root.iter():
        for child in list(parent):
            if child.get("data-role") == "background":
                parent.remove(child)
    return to_string(root)


def with_background(svg: str, color: str) -> str:
    root = parse(svg)
    vb = view_box(root) or (0.0, 0.0, 256.0, 256.0)
    rect = ET.Element(f"{{{SVG_NS}}}rect")
    rect.set("x", f"{vb[0]:g}")
    rect.set("y", f"{vb[1]:g}")
    rect.set("width", f"{vb[2]:g}")
    rect.set("height", f"{vb[3]:g}")
    rect.set("fill", color)
    rect.set("data-role", "background")
    root.insert(0, rect)
    return to_string(root)


def mirrored(svg: str) -> str:
    root = parse(svg)
    vb = view_box(root) or (0.0, 0.0, 256.0, 256.0)
    g = ET.Element(f"{{{SVG_NS}}}g")
    g.set("transform", f"translate({2 * vb[0] + vb[2]:g} 0) scale(-1 1)")
    for child in list(root):
        root.remove(child)
        g.append(child)
    root.append(g)
    return to_string(root)


def blurred_wrapper(svg: str, radius: float = 2.5) -> str:
    """غلاف للاختبار فقط (لا يُسلَّم): يطبّق ضبابًا على العلامة كاملة لاختبار الظل الإدراكي."""
    root = parse(svg)
    vb = view_box(root) or (0.0, 0.0, 256.0, 256.0)
    defs = ET.Element(f"{{{SVG_NS}}}defs")
    flt = ET.SubElement(defs, f"{{{SVG_NS}}}filter")
    flt.set("id", "sima-blur")
    blur = ET.SubElement(flt, f"{{{SVG_NS}}}feGaussianBlur")
    blur.set("stdDeviation", f"{radius * vb[2] / 64:g}")
    g = ET.Element(f"{{{SVG_NS}}}g")
    g.set("filter", "url(#sima-blur)")
    for child in list(root):
        root.remove(child)
        g.append(child)
    root.append(defs)
    root.append(g)
    return to_string(root)


def ensure_title(svg: str, title: str) -> str:
    root = parse(svg)
    has = any(_local(el.tag) == "title" for el in root)
    if not has:
        t = ET.Element(f"{{{SVG_NS}}}title")
        t.text = title
        root.insert(0, t)
    root.set("role", "img")
    return to_string(root)
