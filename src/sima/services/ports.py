"""المنافذ (Protocols) التي تنفّذها المحوّلات. الخدمات لا تستورد المحوّلات مباشرة."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

Gray = list[list[int]]  # صفوف من قيم 0..255


class Renderer(Protocol):
    def render_png(self, svg: str, size: int, background: str | None = None) -> bytes: ...

    def render_gray(self, svg: str, size: int, background: str = "#FFFFFF") -> Gray: ...

    def render_gray_batch(self, svgs: list[str], size: int, background: str = "#FFFFFF") -> list[Gray]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ShapedWord:
    path_d: str  # إحداثيات بوحدات الخط، y لأعلى مقلوب بالفعل (y لأسفل)
    advance: float
    ascender: float
    descender: float
    upem: int
    glyph_count: int


class FontShaper(Protocol):
    def shape(self, text: str, font_path: str, weight: int) -> ShapedWord: ...


@dataclass(frozen=True)
class ReferenceEntry:
    file: str
    brand: str
    svg: str


class Embedder(Protocol):
    """نموذج تضمين محلي: متجه لكل نص بالترتيب، أو None إن كان غير متاح (فيُتجاوز الفحص المعتمد عليه)."""

    model: str

    def embed(self, texts: list[str]) -> list[list[float]] | None: ...


class ReferenceLibrary(Protocol):
    def entries(self) -> list[ReferenceEntry]: ...

    def hashes(self, renderer: Renderer) -> dict[str, dict[str, str]]: ...
