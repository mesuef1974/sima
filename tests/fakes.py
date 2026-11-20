"""مصيّر زائف حتمي للاختبارات: يرسم المستطيلات والدوائر المحورية من SVG بلا Chromium."""
from __future__ import annotations

import re
import struct
import zlib

from sima.services import svgtools
from sima.services.ports import Gray, ReferenceEntry

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _png(width: int, height: int, gray: Gray) -> bytes:
    raw = b"".join(b"\x00" + bytes(row) for row in gray)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class FakeRenderer:
    """يفهم rect وcircle وpath المكوّن من مستطيل M/H/V/Z؛ fill أسود أو أبيض فقط."""

    def __init__(self) -> None:
        self.closed = False

    def _raster(self, svg: str, size: int, background: str) -> Gray:
        root = svgtools.parse(svg)
        vb = svgtools.view_box(root) or (0.0, 0.0, 256.0, 256.0)
        bg = 255 if background.upper() in ("#FFFFFF", "#FFF", "WHITE", "TRANSPARENT") else 0
        g = [[bg] * size for _ in range(size)]
        s = size / max(vb[2], vb[3])
        for el in root.iter():
            tag = el.tag.split("}")[-1]
            fill = (el.get("fill") or "#000000").upper()
            if fill == "NONE":
                continue
            val = 255 if fill in ("#FFFFFF", "#FFF", "WHITE") else 0
            if el.get("data-role") == "background":
                g = [[val] * size for _ in range(size)]
                continue
            if tag == "rect":
                x, y = float(el.get("x", 0)) - vb[0], float(el.get("y", 0)) - vb[1]
                w, h = float(el.get("width", 0)), float(el.get("height", 0))
                self._fill_rect(g, x * s, y * s, w * s, h * s, val, size)
            elif tag == "circle":
                cx, cy, r = float(el.get("cx", 0)) - vb[0], float(el.get("cy", 0)) - vb[1], float(el.get("r", 0))
                for py in range(size):
                    for px in range(size):
                        if ((px + 0.5) / s - cx) ** 2 + ((py + 0.5) / s - cy) ** 2 <= r * r:
                            g[py][px] = val
        return g

    @staticmethod
    def _fill_rect(g: Gray, x: float, y: float, w: float, h: float, val: int, size: int) -> None:
        for py in range(max(0, int(y)), min(size, int(y + h + 0.999))):
            for px in range(max(0, int(x)), min(size, int(x + w + 0.999))):
                if px + 0.5 >= x and px + 0.5 <= x + w and py + 0.5 >= y and py + 0.5 <= y + h:
                    g[py][px] = val

    def render_png(self, svg: str, size: int, background: str | None = None) -> bytes:
        return _png(size, size, self._raster(svg, size, background or "#FFFFFF"))

    def render_gray(self, svg: str, size: int, background: str = "#FFFFFF") -> Gray:
        return self._raster(svg, size, background)

    def render_gray_batch(self, svgs: list[str], size: int, background: str = "#FFFFFF") -> list[Gray]:
        return [self._raster(s, size, background) for s in svgs]

    def close(self) -> None:
        self.closed = True


class FakeLibrary:
    def __init__(self, entries: list[ReferenceEntry]):
        self._entries = entries

    def entries(self) -> list[ReferenceEntry]:
        return self._entries

    def hashes(self, renderer) -> dict[str, dict[str, str]]:
        from sima.services import raster
        out = {}
        for e in self._entries:
            g = renderer.render_gray(e.svg, 32)
            out[e.file] = {"sha": "x", "dhash": raster.dhash(g), "phash": raster.phash(g), "brand": e.brand}
        return out


def rect_svg(x: int, y: int, w: int, h: int, extra: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#000000"/>{extra}</svg>')
