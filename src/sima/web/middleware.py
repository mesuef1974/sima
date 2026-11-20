"""وسيط الجلسات للمنصة: جلسة القاعدة للوحة الإدارة وحدها، فتوقّف القاعدة لا يُسقط صفحات المنصة."""
from __future__ import annotations

from django.contrib.sessions.middleware import SessionMiddleware
from django.db import Error as DatabaseError

ADMIN_PREFIX = "/admin"


class AdminSessionMiddleware(SessionMiddleware):
    """الجلسة تُحفظ وتُمدَّد لطلبات لوحة الإدارة، ولغيرها حين استُعملت فعلًا.

    مع `SESSION_SAVE_EVERY_REQUEST` كان كل طلب من متصفح يحمل كعكة جلسة يقرأ القاعدة في طريق الردّ: قاعدة متوقفة تعني
    انتظار مهلة الاتصال ثم 500 على كل صفحة ومنفذ (var/autostart.log، 2026-11-17)، والمنصة مصادقتها رمز الترويسة لا الجلسة.
    """

    def process_response(self, request, response):
        session = getattr(request, "session", None)
        if session is None or not (request.path.startswith(ADMIN_PREFIX) or session.accessed):
            return response
        try:
            return super().process_response(request, response)
        except DatabaseError:
            if request.path.startswith(ADMIN_PREFIX):
                raise
            return response
