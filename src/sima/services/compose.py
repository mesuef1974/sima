"""تركيب حتمي للتطبيقات: تضمين SVG داخل SVG، ونمط مكرَّر، ونص مشكَّل إلى مسارات بمحاذاة يمين ولفّ أسطر.

النص يُشكَّل بـHarfBuzz عبر منفذ FontShaper، فالتطبيق لا يعتمد على خطوط الجهاز الذي يفتحه.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from xml.sax.saxutils import escape

from . import svgtools
from .ports import FontShaper


def embed(svg: str, x: float, y: float, w: float, h: float, align: str = "xMidYMid") -> str:
    """svg متداخل في صندوق، بنسبة محفوظة."""
    root = svgtools.parse(svg)
    for k in ("width", "height", "x", "y"):
        root.attrib.pop(k, None)
    root.set("x", f"{x:g}")
    root.set("y", f"{y:g}")
    root.set("width", f"{w:g}")
    root.set("height", f"{h:g}")
    root.set("preserveAspectRatio", f"{align} meet")
    return svgtools.to_string(root)


def pattern_def(pid: str, tile_svg: str, size: float) -> str:
    """<pattern> من بلاطة النمط بعرض size مع إبقاء نسبة البلاطة."""
    root = svgtools.parse(tile_svg)
    vb = svgtools.view_box(root) or (0.0, 0.0, 100.0, 100.0)
    w, h = size, size * vb[3] / vb[2]
    inner = "".join(svgtools.to_string(c) for c in root)
    return (f'<pattern id="{pid}" patternUnits="userSpaceOnUse" width="{w:g}" height="{h:g}" '
            f'viewBox="{vb[0]:g} {vb[1]:g} {vb[2]:g} {vb[3]:g}">{inner}</pattern>')


_LTR = re.compile(r"[0-9A-Za-z٠-٩۰-۹]+(?:[ .,:/%+\-][0-9A-Za-z٠-٩۰-۹]+)*")
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def visual_runs(text: str) -> str:
    """HarfBuzz يشكّل المخزن كله باتجاه واحد ولا يطبّق ثنائية الاتجاه؛ في نص عربي تُعكس سلاسل الأرقام واللاتينية
    مسبقًا لتظهر بترتيبها الصحيح من اليسار (١٢ لا ٢١). النص الذي لا عربية فيه يبقى كما هو."""
    if not _ARABIC.search(text):
        return text
    return _LTR.sub(lambda m: m.group(0)[::-1], text)


@dataclass(frozen=True)
class Font:
    file: str
    weight: int


class Typesetter:
    def __init__(self, shaper: FontShaper):
        self._s = shaper
        self._cache: dict[tuple[str, str, int], tuple[str, float, int]] = {}

    def _shape(self, text: str, font: Font) -> tuple[str, float, int]:
        key = (text, font.file, font.weight)
        if key not in self._cache:
            w = self._s.shape(visual_runs(text), font.file, font.weight)
            self._cache[key] = (w.path_d, w.advance, w.upem)
        return self._cache[key]

    def width(self, text: str, font: Font, size: float) -> float:
        _, adv, upem = self._shape(text, font)
        return adv * size / upem

    def line(self, text: str, font: Font, size: float, x: float, baseline: float, fill: str, anchor: str = "end",
             label: str | None = None) -> str:
        """anchor: end = محاذاة يمين عند x (العربية)، start = يسار، middle = وسط."""
        if not text.strip():
            return ""
        d, adv, upem = self._shape(text, font)
        s = size / upem
        w = adv * s
        x0 = x - w if anchor == "end" else (x - w / 2 if anchor == "middle" else x)
        aria = f' aria-label="{escape(label or text)}"'
        return f'<path transform="translate({x0:.2f} {baseline:.2f}) scale({s:.5f})" d="{d}" fill="{fill}"{aria}/>'

    def wrap(self, text: str, font: Font, size: float, max_w: float) -> list[str]:
        lines, cur = [], ""
        for word in text.split():
            cand = f"{cur} {word}".strip()
            if cur and self.width(cand, font, size) > max_w:
                lines.append(cur)
                cur = word
            else:
                cur = cand
        if cur:
            lines.append(cur)
        return lines

    def block(self, text: str, font: Font, size: float, x: float, top: float, max_w: float, fill: str,
              line_height: float = 1.5, anchor: str = "end", max_lines: int = 6) -> tuple[str, float]:
        """فقرة ملفوفة؛ تعيد (svg، أسفل الكتلة)."""
        lines = self.wrap(text, font, size, max_w)[:max_lines]
        out, y = [], top + size
        for ln in lines:
            out.append(self.line(ln, font, size, x, y, fill, anchor))
            y += size * line_height
        return "".join(out), y - size * line_height + size * 0.35


def svg_doc(width: int, height: int, body: str, title: str, defs: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="{escape(title)}"><title>{escape(title)}</title>'
            f'{f"<defs>{defs}</defs>" if defs else ""}{body}</svg>')
