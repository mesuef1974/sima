"""الفكرة والمفهوم والوسيط."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Family(StrEnum):
    LITERAL = "literal"
    METAPHORICAL = "metaphorical"
    ABSTRACT = "abstract"
    TYPOGRAPHIC = "typographic"
    SYMBOLIC = "symbolic"


FAMILY_AR = {
    Family.LITERAL: "حرفي",
    Family.METAPHORICAL: "استعاري",
    Family.ABSTRACT: "مجرد",
    Family.TYPOGRAPHIC: "طباعي",
    Family.SYMBOLIC: "رمزي",
}


class Medium(StrEnum):
    ABSTRACT_MARK = "abstract_mark"
    WORDMARK = "wordmark"
    EMBLEM = "emblem"
    PATTERN = "pattern"


MEDIUM_ORDER: tuple[Medium, ...] = (Medium.ABSTRACT_MARK, Medium.WORDMARK, Medium.EMBLEM, Medium.PATTERN)
MEDIUM_AR = {
    Medium.ABSTRACT_MARK: "علامة مجردة",
    Medium.WORDMARK: "علامة كلامية",
    Medium.EMBLEM: "شارة",
    Medium.PATTERN: "نمط",
}


@dataclass(frozen=True)
class Idea:
    id: str
    family: Family
    sentence: str
    twist: str = ""  # الحيلة: قراءة مزدوجة أو فراغ سلبي أو تحويل غير متوقع


@dataclass(frozen=True)
class Concept:
    id: str
    name: str
    family: Family
    medium: Medium
    sentence: str
    idea_id: str | None = None
    construction: str = ""
    reference: str = ""


def missing_families(concepts: list[Concept]) -> list[Family]:
    covered = {c.family for c in concepts}
    return [f for f in Family if f not in covered]
