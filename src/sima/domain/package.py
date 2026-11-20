"""حزمة الهوية المُصدَّرة."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Package:
    project: str
    version: int
    concept_id: str
    root: Path
    files: tuple[str, ...] = ()

    def path(self, name: str) -> Path:
        return self.root / name
