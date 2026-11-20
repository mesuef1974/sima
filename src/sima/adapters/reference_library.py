"""مكتبة المراجع (vendor/logo-design-skill): قراءة الفهرس وبناء بصمات إدراكية مخبّأة.

العلامات فيها لأصحابها؛ تُستعمل للمقارنة فقط ولا تُنسخ في أي مخرج.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..config import LIBRARY_CATALOG, LIBRARY_HASH_CACHE, LIBRARY_SVG_DIR
from ..services import raster
from ..services.ports import ReferenceEntry, Renderer


class VendoredLibrary:
    def __init__(self, svg_dir: Path = LIBRARY_SVG_DIR, catalog: Path = LIBRARY_CATALOG, cache: Path = LIBRARY_HASH_CACHE):
        self._svg_dir = svg_dir
        self._catalog = catalog
        self._cache = cache

    def available(self) -> bool:
        return self._svg_dir.is_dir()

    def catalog(self) -> list[dict]:
        if not self._catalog.is_file():
            return []
        with self._catalog.open(encoding="utf-8") as fh:
            return json.load(fh)

    def entries(self) -> list[ReferenceEntry]:
        if not self.available():
            return []
        out = []
        for p in sorted(self._svg_dir.glob("*.svg")):
            try:
                out.append(ReferenceEntry(file=p.name, brand=p.stem.removesuffix("-icon"), svg=p.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                continue
        return out

    def hashes(self, renderer: Renderer) -> dict[str, dict[str, str]]:
        """{file: {sha, dhash, phash}} مع تخبئة على القرص؛ يُعاد حساب الملفات المتغيّرة فقط."""
        cache: dict[str, dict[str, str]] = {}
        if self._cache.is_file():
            try:
                cache = json.loads(self._cache.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                cache = {}
        entries = self.entries()
        todo = []
        for e in entries:
            sha = hashlib.sha1(e.svg.encode("utf-8")).hexdigest()[:16]
            if cache.get(e.file, {}).get("sha") != sha:
                todo.append((e, sha))
        if todo:
            grays = renderer.render_gray_batch([e.svg for e, _ in todo], 32, "#FFFFFF")
            for (e, sha), g in zip(todo, grays, strict=True):
                cache[e.file] = {"sha": sha, "dhash": raster.dhash(g), "phash": raster.phash(g), "brand": e.brand}
            keep = {e.file for e in entries}
            cache = {k: v for k, v in cache.items() if k in keep}
            self._cache.parent.mkdir(parents=True, exist_ok=True)
            self._cache.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
        return cache
