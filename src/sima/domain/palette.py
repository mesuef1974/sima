"""لوحة الألوان وأدوارها."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Color:
    name: str
    role: str  # primary | secondary | accent | neutral | system
    hex: str
    informational: bool = True

    @property
    def rgb(self) -> tuple[int, int, int]:
        h = self.hex.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


@dataclass(frozen=True)
class Palette:
    colors: tuple[Color, ...]

    def by_role(self, role: str) -> list[Color]:
        return [c for c in self.colors if c.role == role]

    def get(self, name: str) -> Color:
        for c in self.colors:
            if c.name == name:
                return c
        raise KeyError(name)
