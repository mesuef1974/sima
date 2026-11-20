"""تطبيق اللون على علامة أبيض/أسود: الحبر → لون العلامة، وعناصر data-tone="accent" → لون التمييز."""
from __future__ import annotations

from . import svgtools


def colorize(svg: str, brand: str, accent: str | None = None, *, paper: str | None = None) -> str:
    root = svgtools.parse(svgtools.strip_background(svg))
    for el in root.iter():
        tone = el.get("data-tone")
        if tone == "accent" and accent:
            for attr in ("fill", "stroke"):
                v = el.get(attr)
                if v and v.strip().lower() not in ("none", "transparent"):
                    el.set(attr, accent)
        elif tone == "paper" and paper:
            for attr in ("fill", "stroke"):
                v = el.get(attr)
                if v and v.strip().lower() not in ("none", "transparent"):
                    el.set(attr, paper)
    s = svgtools.to_string(root)
    mapping = {"#000000": brand}
    if accent:
        mapping[svgtools.normalize_hex(accent)] = accent
    if paper:
        mapping[svgtools.normalize_hex(paper)] = paper
    mapping["#FFFFFF"] = paper or "#FFFFFF"
    return svgtools.recolor(s, mapping, keep_background=False)
