"""العلامة: نص SVG لمفهوم في صيغة محددة."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Variant(StrEnum):
    PRIMARY = "primary"
    MONO = "mono"
    REVERSED = "reversed"
    BLURRED = "blurred"
    MIRRORED = "mirrored"
    WORDMARK = "wordmark"
    LOCKUP = "lockup"


@dataclass(frozen=True)
class Mark:
    concept_id: str
    variant: Variant
    svg: str
    round: int = 0

    @property
    def filename(self) -> str:
        return f"{self.concept_id}-{self.variant.value}.svg"
