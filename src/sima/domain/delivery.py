"""تسليم الحزمة المعتمدة إلى مستودع المشروع عبر «المشغّل» (بطاقة في دفتر automation/ledger).

سِمة لا تدفع ولا تفتح طلب دمج: تكتب الملفات في worktree على فرع البطاقة وتضع البطاقة ready،
والمشغّل المجدوَل في المستودع الهدف هو من يفحص ويدفع ويفتح الطلب.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FileWrite:
    """ملف يُكتب في المستودع الهدف (مسار نسبي من جذر المستودع)."""
    path: str
    content: bytes


@dataclass(frozen=True)
class DeliveryPlan:
    project: str
    version: int
    concept_id: str
    writes: tuple[FileWrite, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)  # ما تغيّر، يُكتب في بطاقة المشغّل
    deletes: tuple[str, ...] = ()  # ملفات هوية سابقة في المستودع ليست في الهوية المعتمدة الآن

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(w.path for w in self.writes)


@dataclass(frozen=True)
class DeliveryReceipt:
    card_id: str
    branch: str
    worktree: str
    head: str
    paths: tuple[str, ...]
    changed: tuple[str, ...] = ()  # ما تغيّر محتواه فعلًا من مسارات الخطة، ومعه ما حُذف
    deleted: tuple[str, ...] = ()  # ما حُذف من ملفات هوية سابقة (من `changed`)


def applied(marker: dict) -> bool:
    """تسليم بلا بطاقة سُجّل بنقطة git مدموجة: في مستودع سِمة نفسه (`in_place`) أو يدويًّا في مستودع المشروع (`manual`).
    كلاهما تسليم ودمج معًا، فلا دفتر يُقرأ ولا فرع يُكتشف."""
    return bool(marker.get("in_place") or marker.get("manual"))
