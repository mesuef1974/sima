"""تشكيل عربي: uharfbuzz للتشكيل، fonttools للحدود، skia-pathops لإزالة التداخل."""
from __future__ import annotations

import contextlib
import unicodedata
from functools import lru_cache
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from pathops import Path as SkPath
from pathops import PathOp, PathOpsError, op

from ..config import FONTS_DIR
from ..services.ports import ShapedWord


def resolve_font(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.is_file():
        return p
    cand = FONTS_DIR / name_or_path
    if cand.is_file():
        return cand
    raise FileNotFoundError(f"الخط غير موجود: {name_or_path} (ابحث في {FONTS_DIR})")


@lru_cache(maxsize=8)
def _instance(path: str, weight: int) -> TTFont:
    tt = TTFont(path)
    if "fvar" in tt:
        axes = {a.axisTag: a for a in tt["fvar"].axes}
        loc = {}
        if "wght" in axes:
            a = axes["wght"]
            loc["wght"] = min(max(weight, a.minValue), a.maxValue)
        for tag, a in axes.items():
            if tag != "wght":
                loc[tag] = a.defaultValue
        tt = instantiateVariableFont(tt, loc, inplace=False)
    return tt


class HarfBuzzShaper:
    """ينفّذ FontShaper: يُخرج مسارًا واحدًا بإحداثيات y لأسفل (مقلوب) ومتحدًا بلا تداخل."""

    def shape(self, text: str, font_path: str, weight: int) -> ShapedWord:
        path = str(resolve_font(font_path))
        blob = hb.Blob.from_file_path(path)
        face = hb.Face(blob)
        font = hb.Font(face)
        upem = face.upem
        with contextlib.suppress(Exception):
            font.set_variations({"wght": float(weight)})
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, {"kern": True, "liga": True, "calt": True, "rlig": True})
        tt = _instance(path, weight)
        gs = tt.getGlyphSet()
        order = tt.getGlyphOrder()
        sk = SkPath()
        pen = sk.getPen(glyphSet=gs)
        parts: list[SkPath] = []
        x = 0.0
        n = 0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions, strict=True):
            name = order[info.codepoint]
            m = (1, 0, 0, -1, x + pos.x_offset, -pos.y_offset)
            gs[name].draw(TransformPen(pen, m))
            g = SkPath()
            gs[name].draw(TransformPen(g.getPen(glyphSet=gs), m))
            with contextlib.suppress(PathOpsError):  # حرف تعذّر تبسيطه يبقى بمحيطه كما في الخط
                g.simplify(fix_winding=True)
            parts.append(g)
            x += pos.x_advance
            n += 1
        # pathops يُسقط أحيانًا حرفًا كاملًا عند توحيد حروف متلامسة (Cairo مثلًا)، أو يتعذّر عليه التوحيد كله فيرمي
        # (Cairo في عنوان اتجاه «مسك» v5، 2026-11-17). كل حرف يجب أن يغطيه الناتج؛ فإن تعذّر التوحيد أو خرج من حرف أكثر
        # من 2% من مساحته تُضمّ الحروف الموحّدة منفردةً بدل التوحيد الكلي.
        try:
            sk.simplify(fix_winding=True)
            whole = not any(g.area and abs(op(g, sk, PathOp.DIFFERENCE, fix_winding=False).area) > 0.02 * abs(g.area) for g in parts)
        except PathOpsError:
            whole = False
        if not whole:
            sk = SkPath()
            for g in parts:
                g.draw(sk.getPen())
        out = SVGPathPen(None)
        sk.draw(out)
        hhea = tt["hhea"]
        return ShapedWord(
            path_d=out.getCommands(),
            advance=x,
            ascender=float(hhea.ascent),
            descender=float(hhea.descent),
            upem=upem,
            glyph_count=n,
        )


PARTS = ("all", "letters", "marks", "dots")


def shape_parts(text: str, font_path: str, weight: int, size: float, x: float, base: float, part: str = "all") -> SkPath:
    """الكلمة مشكّلة بـ HarfBuzz مسارًا بإحداثيات أداة البناء (y لأسفل): size ارتفاع الـ em بالوحدات، و(x, base) بداية
    خط القاعدة. part يختار جزءًا ليُعدَّل وحده: letters (الحروف بنقاطها)، marks (الحركات كالكسرة)، dots (نقاط الإعجام)."""
    if part not in PARTS:
        raise ValueError(f"part من {list(PARTS)}")
    path = str(resolve_font(font_path))
    face = hb.Face(hb.Blob.from_file_path(path))
    font = hb.Font(face)
    with contextlib.suppress(Exception):
        font.set_variations({"wght": float(weight)})
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    # كل حركة في عنقودها الخاص: يُعرف الجزء من حرف يونيكود الأصل لا من صنف الحرف في الخط
    buf.cluster_level = hb.BufferClusterLevel.MONOTONE_CHARACTERS
    hb.shape(font, buf, {"kern": True, "liga": True, "calt": True, "rlig": True})
    tt = _instance(path, weight)
    gs, order = tt.getGlyphSet(), tt.getGlyphOrder()
    gdef = tt["GDEF"].table.GlyphClassDef.classDefs if "GDEF" in tt and tt["GDEF"].table.GlyphClassDef else {}
    k = size / face.upem
    out, adv = SkPath(), 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions, strict=True):
        name = order[info.codepoint]
        haraka = unicodedata.category(text[info.cluster]).startswith("M") if info.cluster < len(text) else False
        # نقاط تفصلها بعض الخطوط حرفًا مستقلًا (ريم كوفي): صنفها mark في الخط لكن أصلها حرف لا حركة
        dot_glyph = not haraka and gdef.get(name) == 3
        m = (k, 0, 0, -k, x + (adv + pos.x_offset) * k, base - pos.y_offset * k)
        adv += pos.x_advance
        if (part == "marks" and not haraka) or (part in ("letters", "dots") and haraka):
            continue
        g = SkPath()
        gs[name].draw(TransformPen(g.getPen(glyphSet=gs), m))
        g.simplify(fix_winding=True)
        if part == "dots" and not dot_glyph:
            g = _dots(g)
        g.draw(out.getPen())
    out.simplify(fix_winding=True)
    return out


def _dots(g: SkPath) -> SkPath:
    """نقاط الإعجام: المكوّنات المنفصلة الصغيرة في الحرف (أصغر من 12% من مساحة إطار أكبر مكوّن)."""
    comps = []
    for c in g.contours:
        q = SkPath()
        c.draw(q.getPen())
        b = q.bounds
        comps.append((q, (b[2] - b[0]) * (b[3] - b[1]), c.clockwise, b))
    if len(comps) < 2:
        return SkPath()
    big = max(comps, key=lambda t: t[1])
    outer = [t for t in comps if t[2] == big[2]]  # الثقوب (فراغ الميم والتاء) عكس اتجاه الكفاف الخارجي فليست نقاطًا

    def inside(b, o) -> bool:
        return b[0] >= o[0] and b[1] >= o[1] and b[2] <= o[2] and b[3] <= o[3]

    out = SkPath()
    for q, a, _, b in outer:
        if a < 0.12 * big[1] and not any(o is not q and inside(b, ob) for o, _, _, ob in outer):
            q.draw(out.getPen())
    return out
