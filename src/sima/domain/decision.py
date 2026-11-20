"""قرارات المالك والوسيط الحالي."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .concept import MEDIUM_ORDER, Medium


class Verdict(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISE = "revise"
    SWITCH = "switch_medium"  # المالك يختار وسيطًا آخر؛ medium في القرار هو الوسيط الجديد


@dataclass(frozen=True)
class Decision:
    concept_id: str | None
    verdict: Verdict
    medium: Medium
    reason: str
    at: str  # ISO 8601
    round: int = 0


@dataclass
class MediumLock:
    """الوسيط الحالي. منذ 2026-11-09 لا يتغيّر إلا باختيار المالك (قرار SWITCH)؛ الرفض يقود إعادة الرسم في الوسيط نفسه.
    التدوير القديم (الرفض الثالث يقفل الوسيط ويفتح التالي) باقٍ خلف auto_rotate لقراءة سجلات قديمة واختباراتها فقط."""

    rejections: dict[Medium, int] = field(default_factory=dict)
    locked: list[Medium] = field(default_factory=list)
    limit: int = 3
    auto_rotate: bool = False
    chosen: Medium | None = None

    def record(self, decision: Decision) -> None:
        if decision.verdict is Verdict.SWITCH:
            self.chosen = decision.medium
            return
        if decision.verdict is not Verdict.REJECTED:
            return
        n = self.rejections.get(decision.medium, 0) + 1
        self.rejections[decision.medium] = n
        if self.auto_rotate and n >= self.limit and decision.medium not in self.locked:
            self.locked.append(decision.medium)

    def is_locked(self, medium: Medium) -> bool:
        return medium in self.locked

    def current(self) -> Medium | None:
        if self.chosen is not None:
            return self.chosen
        for m in MEDIUM_ORDER:
            if m not in self.locked:
                return m
        return None

    @classmethod
    def from_decisions(cls, decisions: list[Decision], limit: int = 3, auto_rotate: bool = False) -> MediumLock:
        lock = cls(limit=limit, auto_rotate=auto_rotate)
        for d in decisions:
            lock.record(d)
        return lock
