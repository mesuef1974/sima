"""طبقة Django لسِمة: قاعدة البيانات العلائقية (PostgreSQL) وواجهة الـAPI. محوّل فوق النواة لا بديل عنها."""
from __future__ import annotations

import os


def setup() -> None:
    """يهيّئ Django مرة واحدة لأي أمر يحتاج قاعدة البيانات."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sima.web.settings")
    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()
