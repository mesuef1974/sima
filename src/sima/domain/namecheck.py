"""التحقق من توافر الاسم: سجلّ يدوي يملؤه المالك بعد البحث في السجلات الرسمية.

الأداة لا تتصل بالشبكة (المعالجة محلية)؛ هي تكتب قائمة التحقق بروابطها، والمالك يسجّل النتيجة.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class NameStatus(StrEnum):
    PENDING = "pending"  # لم يُتحقَّق بعد
    CLEAR = "clear"  # لا تعارض في المصادر المفحوصة
    CONFLICT = "conflict"  # يوجد تعارض؛ يلزم اسم آخر


NAME_STATUS_AR = {
    NameStatus.PENDING: "بانتظار التحقق",
    NameStatus.CLEAR: "متاح في المصادر المفحوصة",
    NameStatus.CONFLICT: "متعارض",
}


@dataclass(frozen=True)
class NameCheck:
    name: str  # الاسم المفحوص (الاسم القصير / نص الكلمة)
    status: NameStatus
    checked_at: str  # ISO-8601
    sources: tuple[str, ...] = ()  # المصادر التي فُحصت فعليًا (روابط أو أسماء سجلات)
    note: str = ""

    @property
    def blocks_package(self) -> bool:
        return self.status is not NameStatus.CLEAR
