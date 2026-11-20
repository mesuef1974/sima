"""خدمة التصيير: لكل مفهوم PNG بالأحجام 16/32/48/256 ونسخ أحادية ومعكوسة ومشوّشة وممرآة."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .. import config
from ..domain import Variant
from . import svgtools
from .ports import Renderer


@dataclass
class RenderResult:
    concept_id: str
    files: dict[str, str] = field(default_factory=dict)  # اسم منطقي → مسار

    def to_dict(self) -> dict:
        return {"concept_id": self.concept_id, "files": self.files}


class RenderService:
    def __init__(self, renderer: Renderer):
        self._r = renderer

    def variants(self, svg: str) -> dict[Variant, str]:
        return {
            Variant.PRIMARY: svg,
            Variant.MONO: svgtools.mono(svg),
            Variant.REVERSED: svgtools.reversed_(svg),
            Variant.MIRRORED: svgtools.mirrored(svg),
            Variant.BLURRED: svgtools.blurred_wrapper(svg),
        }

    def render_concept(self, concept_id: str, svg: str, out_dir: Path) -> RenderResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        res = RenderResult(concept_id=concept_id)
        for size in config.RENDER_SIZES:
            p = out_dir / f"{size}.png"
            p.write_bytes(self._r.render_png(svg, size, "#FFFFFF"))
            res.files[str(size)] = str(p)
        for var, vsvg in self.variants(svg).items():
            if var is Variant.PRIMARY:
                continue
            bg = None if var is Variant.REVERSED else "#FFFFFF"
            p = out_dir / f"{var.value}.png"
            p.write_bytes(self._r.render_png(vsvg, 256, bg))
            res.files[var.value] = str(p)
        return res
