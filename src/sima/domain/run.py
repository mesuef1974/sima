"""مفتاح التشغيل: hash الموجز + seed، قابل لإعادة الإنتاج."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunKey:
    project: str
    brief_hash: str
    seed: int

    @property
    def key(self) -> str:
        return f"{self.brief_hash}-s{self.seed}"
