"""خادم منصة سِمة: Django عبر wsgiref متعدد الخيوط على 127.0.0.1 فقط، لمستخدم واحد وبلا حزمة خادم إضافية."""
from __future__ import annotations

import sys
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server


class _Threading(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class _Quiet(WSGIRequestHandler):
    def log_message(self, *_args) -> None:  # صامت
        return

    def log_request(self, code="-", size="-") -> None:
        """الطلبات الناجحة صامتة؛ أخطاء الخادم تُكتب بسطر الطلب كي يُعرف ما فشل ومن أين."""
        if str(getattr(code, "value", code)).startswith("5"):
            ua = self.headers.get("User-Agent", "")[:80] if self.headers else ""
            sys.stderr.write(f"[{code}] {self.requestline} | {ua}\n")
            sys.stderr.flush()


def serve(host: str = "127.0.0.1", port: int = 8766) -> None:
    from . import setup

    setup()
    from django.core.wsgi import get_wsgi_application

    httpd = make_server(host, port, get_wsgi_application(), server_class=_Threading, handler_class=_Quiet)
    print(f"منصة سِمة: http://{host}:{port}  (Ctrl+C للإيقاف)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
