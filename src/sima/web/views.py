"""صفحة المنصة (قالب يحمّل حزمة Vue عبر django-vite ويحقن رمز التشغيل) وملفات المخرجات والخطوط للقراءة فقط."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from ..config import FONTS_DIR
from ..services.board import safe_out_path
from . import runtime

TYPES = {".svg": "image/svg+xml", ".webmanifest": "application/manifest+json", ".md": "text/plain; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".html": "text/html; charset=utf-8",
         ".vue": "text/plain; charset=utf-8", ".ico": "image/x-icon",
         ".webp": "image/webp"}  # سجل ويندوز قد يخلو منه فيُخدم octet-stream ولا يُعرض


# ملفات out/ تُخدم من أصل المنصة، وبعضها كتبه النموذج (رسوم المفاهيم في work/). فتُعزل في sandbox بأصل مُعتم: لا تصل إلى
# رمز التشغيل ولا تستطيع إرسال طلب (connect-src 'none' وform-action 'none'). مستندات سِمة المولّدة (عرض الكشف) يُسمح لها
# بنصها المضمّن فقط؛ وما كتبه النموذج بلا أي نص.
OUT_CSP_DOC = ("sandbox allow-scripts allow-popups; default-src 'none'; script-src 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
               "img-src 'self' data: blob:; font-src 'self' data:; media-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'")
OUT_CSP_MODEL = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src 'self'"
ISOLATED = {".html", ".htm", ".svg", ".xml", ".xhtml"}


def _out_csp(rel: str, suffix: str) -> str | None:
    if suffix not in ISOLATED:
        return None
    parts = [x.lower() for x in rel.replace("\\", "/").split("/") if x]
    return OUT_CSP_MODEL if "work" in parts else OUT_CSP_DOC


def _no_store(r: HttpResponse) -> HttpResponse:
    r["Cache-Control"] = "no-store"
    r["X-Content-Type-Options"] = "nosniff"
    return r


_MANIFEST_SEEN: dict[str, int | None] = {"mtime": None}


def refresh_manifest(path: Path | None = None) -> bool:
    """django-vite يقرأ بيان البناء مرة عند أول استعمال؛ فإن أُعيد بناء الواجهة والخادم يعمل ظهرت الصفحة بلا أنماط (404 على ملفات
    مجزّأة قديمة). نقارن زمن البيان في كل طلب للصفحة ونُسقط المحمّل المخزَّن عند تغيّره، فلا تلزم إعادة التشغيل بعد كل بناء."""
    path = path or Path(settings.DJANGO_VITE["default"]["manifest_path"])
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return False
    if stamp == _MANIFEST_SEEN["mtime"]:
        return False
    _MANIFEST_SEEN["mtime"] = stamp
    from django_vite.core.asset_loader import DjangoViteAssetLoader

    DjangoViteAssetLoader._instance = None
    return True


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    refresh_manifest()
    r = render(request, "sima/board.html", {"token": runtime.TOKEN})
    dev = " ws://127.0.0.1:5173 http://127.0.0.1:5173" if settings.DJANGO_VITE["default"]["dev_mode"] else ""
    r["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                    f"font-src 'self'; frame-src 'self'; connect-src 'self'{dev}; "
                                    f"script-src 'self'{dev.replace(' ws://127.0.0.1:5173', '')}; base-uri 'none'; form-action 'none'")
    r["Referrer-Policy"] = "no-referrer"
    return _no_store(r)


@require_GET
def out_file(request: HttpRequest, rel: str) -> HttpResponse:
    target = safe_out_path(runtime.out_dir(), rel)
    if target is None:
        raise Http404
    ctype = TYPES.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    r = FileResponse(target.open("rb"), content_type=ctype)
    csp = _out_csp(rel, target.suffix.lower())
    if csp:
        r["Content-Security-Policy"] = csp
        r["Referrer-Policy"] = "no-referrer"
    if target.suffix.lower() in (".ttf", ".otf", ".woff", ".woff2"):
        r["Access-Control-Allow-Origin"] = "*"  # خطوط OFL عامة؛ يحتاجها المستند المعزول بأصله المُعتم
    return _no_store(r)


@require_GET
def font(request: HttpRequest, name: str) -> HttpResponse:
    f = FONTS_DIR / name
    if "/" in name or "\\" in name or not name.endswith(".ttf") or not f.is_file():
        raise Http404
    r = FileResponse(f.open("rb"), content_type="font/ttf")
    r["Cache-Control"] = "public, max-age=86400"
    return r
