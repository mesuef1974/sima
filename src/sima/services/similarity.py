"""تشابه إدراكي: بصمتا dHash وpHash للعلامة مقابل بصمات المكتبة المرجعية."""
from __future__ import annotations

from . import raster
from .ports import ReferenceLibrary, Renderer


class SimilarityService:
    def __init__(self, renderer: Renderer, library: ReferenceLibrary | None):
        self._r = renderer
        self._lib = library
        self._index: dict[str, dict[str, str]] | None = None

    def index(self) -> dict[str, dict[str, str]]:
        if self._index is None:
            self._index = self._lib.hashes(self._r) if self._lib is not None else {}
        return self._index

    def fingerprint(self, svg: str) -> dict[str, str]:
        g = self._r.render_gray(svg, 32, "#FFFFFF")
        return {"dhash": raster.dhash(g), "phash": raster.phash(g)}

    @staticmethod
    def distance(a: dict[str, str], b: dict[str, str]) -> int:
        """المسافة المركّبة: الأدنى من البصمتين (أي تطابق في إحداهما مقلق)."""
        return min(raster.hamming(a["dhash"], b["dhash"]), raster.hamming(a["phash"], b["phash"]))

    def nearest(self, svg: str, top: int = 3) -> list[dict]:
        idx = self.index()
        if not idx:
            return []
        fp = self.fingerprint(svg)
        scored = [
            {"file": f, "brand": h.get("brand", f), "distance": self.distance(fp, h)}
            for f, h in idx.items()
        ]
        scored.sort(key=lambda d: (d["distance"], d["file"]))
        return scored[:top]

    def pairwise(self, svgs: dict[str, str]) -> list[dict]:
        """تشابه المفاهيم بعضها ببعض؛ مفهومان متقاربان ليسا «متباعدين»."""
        fps = {k: self.fingerprint(v) for k, v in svgs.items()}
        keys = sorted(fps)
        out = []
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                out.append({"a": a, "b": b, "distance": self.distance(fps[a], fps[b])})
        return out
