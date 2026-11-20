"""محوّل التضمين المحلي: نموذج تضمين (bge-m3) في LM Studio على هذا الجهاز عبر واجهة متوافقة مع OpenAI.

محلي بالكامل: العنوان يُرفض إن لم يكن حلقة محلية (127.0.0.1 أو localhost). بلا حزم جديدة (urllib). الخادم المتوقف ليس
خطأ: embed يعيد None فيُتجاوز الفحص الذي يعتمد عليه. يُوقف بـ SIMA_EMBED=0.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _env(key: str, default: str) -> str:
    from .. import config  # القارئ الوحيد للبيئة: .env ثم متغيرات البيئة، بلا إعدادات Django

    return config.ENV.get(key, default)


def enabled() -> bool:
    return _env("SIMA_EMBED", "1") == "1"


class LocalEmbedder:
    def __init__(self, url: str | None = None, model: str | None = None, timeout_s: float | None = None):
        self._url = (url or _env("SIMA_LOCAL_URL", "http://127.0.0.1:1234/v1")).rstrip("/")
        host = urlparse(self._url).hostname or ""
        if host not in LOOPBACK:
            raise ValueError(f"عنوان النموذج المحلي يجب أن يكون على هذا الجهاز (127.0.0.1)، لا {host or self._url}")
        self.model = model or _env("SIMA_EMBED_MODEL", "text-embedding-bge-m3")
        self._timeout = timeout_s if timeout_s is not None else float(_env("SIMA_EMBED_TIMEOUT_S", "30"))

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """متجه لكل نص بالترتيب، أو None إن كان الخادم متوقفًا أو ردّه غير صالح."""
        if not texts:
            return []
        body = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        # العنوان محصور في الحلقة المحلية في __init__، فلا مخطط ولا وجهة غير متوقعة هنا
        req = urllib.request.Request(self._url + "/embeddings", data=body, headers={"Content-Type": "application/json"})  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:  # noqa: S310
                data = json.loads(r.read().decode("utf-8"))
            rows = sorted(data["data"], key=lambda d: d["index"])
            out = [[float(x) for x in d["embedding"]] for d in rows]
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, TypeError, ValueError):
            return None
        return out if len(out) == len(texts) and all(out) else None
