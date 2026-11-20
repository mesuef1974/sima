"""تشكيل الكلمة العربية إلى مسارات SVG بلا <text>، وتركيب العلامة الكلامية والقفل الأفقي."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .ports import FontShaper, ShapedWord
from .svgtools import parse, strip_background, to_string, view_box


@dataclass(frozen=True)
class WordmarkSVG:
    svg: str
    width: float
    height: float
    path_d: str


_TOKENS = re.compile(r"[MLHVQCZmlhvqcz]|-?\d+(?:\.\d+)?(?:e-?\d+)?")


def _walk(d: str):
    """يولّد (الأمر، قائمة الإحداثيات) مع تحديد أي الأرقام x وأيها y؛ يدعم M/L/H/V/Q/C/Z المطلقة."""
    cmd = None
    buf: list[float] = []
    for t in _TOKENS.findall(d):
        if t.isalpha():
            if cmd is not None:
                yield cmd, buf
            cmd, buf = t.upper(), []
        else:
            buf.append(float(t))
    if cmd is not None:
        yield cmd, buf


def _path_bbox(d: str) -> tuple[float, float, float, float]:
    """صندوق تقريبي من نقاط التحكم (كافٍ لضبط الهوامش)."""
    xs: list[float] = []
    ys: list[float] = []
    cx = cy = 0.0
    for cmd, nums in _walk(d):
        if cmd == "H":
            xs.extend(nums)
            cx = nums[-1] if nums else cx
        elif cmd == "V":
            ys.extend(nums)
            cy = nums[-1] if nums else cy
        elif cmd != "Z":
            xs.extend(nums[0::2])
            ys.extend(nums[1::2])
            if nums:
                cx, cy = nums[-2], nums[-1]
    return min(xs), min(ys), max(xs), max(ys)


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _scale(v: float) -> str:
    """معامل التكبير بست خانات: خانتان تزيحان رمزًا نافذته بالمئات (متجه مصمّم خارجي) بكسلات عن موضعه."""
    return f"{v:.6f}".rstrip("0").rstrip(".")


def _scale_path(d: str, s: float, dx: float, dy: float) -> str:
    """تحجيم مسار بأوامر مطلقة M/L/H/V/Q/C/Z (كما يُخرجه SVGPathPen) إلى أوامر M/L/Q/C/Z."""
    out: list[str] = []
    for cmd, nums in _walk(d):
        if cmd == "Z":
            out.append("Z")
        elif cmd == "H":
            out.append("H " + " ".join(_fmt(v * s + dx) for v in nums))
        elif cmd == "V":
            out.append("V " + " ".join(_fmt(v * s + dy) for v in nums))
        else:
            coords = [_fmt(v * s + (dx if i % 2 == 0 else dy)) for i, v in enumerate(nums)]
            out.append(cmd + " " + " ".join(coords))
    return " ".join(out)


_INHERITED = ("fill", "fill-rule", "clip-rule", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin")


class ShapingService:
    """يحوّل كلمة إلى علامة كلامية SVG؛ الحساب حتمي لنفس الخط والوزن."""

    def __init__(self, shaper: FontShaper):
        self._shaper = shaper

    def shape(self, text: str, font_path: str, weight: int) -> ShapedWord:
        return self._shaper.shape(text, font_path, weight)

    def wordmark(self, text: str, font_path: str, weight: int, *, height: float = 256.0, padding: float = 0.08,
                 fill: str = "#000000", title: str | None = None) -> WordmarkSVG:
        word = self._shaper.shape(text, font_path, weight)
        if not word.path_d.strip():
            raise ValueError("التشكيل لم يُنتج مسارًا")
        x0, y0, x1, y1 = _path_bbox(word.path_d)
        glyph_h = max(y1 - y0, 1.0)
        inner_h = height * (1 - 2 * padding)
        s = inner_h / glyph_h
        pad = height * padding
        d = _scale_path(word.path_d, s, -x0 * s + pad, -y0 * s + pad)
        width = (x1 - x0) * s + 2 * pad
        t = f"<title>{title}</title>" if title else ""
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(width)} {_fmt(height)}" role="img">{t}'
            f'<path id="wordmark" fill="{fill}" fill-rule="nonzero" d="{d}"/></svg>'
        )
        return WordmarkSVG(svg=svg, width=width, height=height, path_d=d)

    @staticmethod
    def lockup(mark_svg: str, wordmark: WordmarkSVG, *, gap_ratio: float = 0.25, word_height_ratio: float = 0.62,
               rtl: bool = True) -> str:
        """قفل أفقي: الرمز والكلمة على سطر واحد؛ في RTL الرمز على اليمين والكلمة على يساره."""
        mark_root = parse(strip_background(mark_svg))
        mvb = view_box(mark_root) or (0.0, 0.0, 256.0, 256.0)
        H = 256.0
        ms = H / mvb[3]
        mark_w = mvb[2] * ms
        gap = H * gap_ratio
        word_h = H * word_height_ratio
        ws = word_h / wordmark.height
        word_w = wordmark.width * ws
        total_w = mark_w + gap + word_w
        word_y = (H - word_h) / 2
        if rtl:
            mark_x, word_x = total_w - mark_w, 0.0
        else:
            mark_x, word_x = 0.0, mark_w + gap
        for el in mark_root.iter():  # رمز اعتُمد من خارج الخط مغلَّف بمعرّف الكلمة: في القفل هو الرمز، والكلمة ما يليه
            if el.get("id") == "wordmark":
                del el.attrib["id"]
        # ألوان الرمز وحدوده المعرَّفة على جذره تنتقل إلى مجموعته، وإلا ورثت مساراته الأسود الافتراضي ولم تتلوّن
        style = "".join(f' {a}="{mark_root.get(a)}"' for a in _INHERITED if mark_root.get(a))
        inner = "".join(to_string(ch) for ch in list(mark_root) if not ch.tag.endswith("}title"))
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(total_w)} {_fmt(H)}" role="img">'
            f'<g id="symbol"{style} transform="translate({_fmt(mark_x - mvb[0] * ms)} {_fmt(-mvb[1] * ms)}) scale({_scale(ms)})">{inner}</g>'
            f'<g id="wordmark" transform="translate({_fmt(word_x)} {_fmt(word_y)}) scale({_scale(ws)})">'
            f'<path fill="#000000" d="{wordmark.path_d}"/></g></svg>'
        )
