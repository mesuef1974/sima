"""محوّل Recraft (استدعاء سحابي) معطّل افتراضيًا.

يُفعَّل فقط بـ SIMA_ENABLE_RECRAFT=1 وبمفتاح RECRAFT_API_KEY، ويُعلَن في سجل التشغيل عند التفعيل.
لا يُرسَل أي شيء خارج الجهاز بدون ذلك. غير مُستعمل في خط الإنتاج الحالي.
"""
from __future__ import annotations

import os


class RecraftDisabled(RuntimeError):
    pass


def enabled() -> bool:
    return os.environ.get("SIMA_ENABLE_RECRAFT") == "1" and bool(os.environ.get("RECRAFT_API_KEY"))


def vectorize(prompt: str) -> str:
    if not enabled():
        raise RecraftDisabled("Recraft معطّل: المعالجة محلية بالكامل. فعّله صراحة بـ SIMA_ENABLE_RECRAFT=1 إن أردت.")
    raise NotImplementedError("لم يُنفَّذ الاستدعاء؛ المحوّل مكان محفوظ فقط.")
