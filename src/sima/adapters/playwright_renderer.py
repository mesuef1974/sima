"""تصيير SVG عبر Chromium بلا نافذة (Playwright). يُغلق المتصفح آليًا عند الخروج أو close()."""
from __future__ import annotations

import atexit
import base64
import contextlib
import json
import os
from pathlib import Path

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from ..config import BROWSERS_DIR
from ..services.ports import Gray

_GRAY_JS = """
async ([svgs, size, background]) => {
  const out = [];
  const c = document.createElement('canvas'); c.width = size; c.height = size;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  for (const svg of svgs) {
    const img = new Image();
    const url = 'data:image/svg+xml;base64,' + svg;
    await new Promise((res, rej) => { img.onload = res; img.onerror = () => res(); img.src = url; });
    ctx.clearRect(0, 0, size, size);
    if (background) { ctx.fillStyle = background; ctx.fillRect(0, 0, size, size); }
    // contain: نحافظ على النسبة ونوسّط
    const iw = img.naturalWidth || size, ih = img.naturalHeight || size;
    const s = Math.min(size / iw, size / ih);
    const w = iw * s, h = ih * s;
    try { ctx.drawImage(img, (size - w) / 2, (size - h) / 2, w, h); } catch (e) {}
    const d = ctx.getImageData(0, 0, size, size).data;
    const rows = [];
    for (let y = 0; y < size; y++) {
      const row = new Array(size);
      for (let x = 0; x < size; x++) {
        const i = (y * size + x) * 4;
        const a = d[i + 3] / 255;
        // دمج مع أبيض إن لم تكن خلفية
        const r = d[i] * a + 255 * (1 - a), g = d[i + 1] * a + 255 * (1 - a), b = d[i + 2] * a + 255 * (1 - a);
        row[x] = Math.round(0.2126 * r + 0.7152 * g + 0.0722 * b);
      }
      rows.push(row);
    }
    out.push(rows);
  }
  return out;
}
"""

_HTML = "<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;padding:0;background:transparent}#box{display:block}</style></head><body><div id='box'></div></body></html>"


def browsers_env(folder: Path = BROWSERS_DIR, environ=os.environ) -> str | None:
    """يوجّه Playwright إلى متصفح المشروع إن وُجد ولم يحدّد المالك مسارًا. يعيد المسار المعتمد أو None (الافتراضي)."""
    if not environ.get("PLAYWRIGHT_BROWSERS_PATH") and folder.is_dir() and any(folder.iterdir()):
        environ["PLAYWRIGHT_BROWSERS_PATH"] = str(folder)
    return environ.get("PLAYWRIGHT_BROWSERS_PATH")


class PlaywrightRenderer:
    """ينفّذ Renderer. يفتح Chromium مرة واحدة ويُعيد استعماله."""

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        atexit.register(self.close)

    def _ensure(self) -> Page:
        if self._page is None:
            where = browsers_env()
            self._pw = sync_playwright().start()
            try:
                self._browser = self._pw.chromium.launch(headless=True, args=["--disable-gpu"])
            except Exception as e:
                self.close()
                raise RuntimeError(
                    f"تعذّر تشغيل Chromium للتصيير (مسار المتصفحات: {where or 'الافتراضي'}). ضع المتصفح في {BROWSERS_DIR} "
                    f"بأمر PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH='{BROWSERS_DIR}'; uv run playwright install chromium-headless-shell"
                ) from e
            self._page = self._browser.new_page(viewport={"width": 1024, "height": 1024}, device_scale_factor=1)
            self._page.set_content(_HTML)
        return self._page

    @staticmethod
    def _b64(svg: str) -> str:
        return base64.b64encode(svg.encode("utf-8")).decode("ascii")

    def render_png(self, svg: str, size: int, background: str | None = None) -> bytes:
        page = self._ensure()
        bg = background or "transparent"
        html = (
            f"<div id='box' style='width:{size}px;height:{size}px;background:{bg};display:flex;align-items:center;justify-content:center'>"
            f"<img src='data:image/svg+xml;base64,{self._b64(svg)}' style='max-width:{size}px;max-height:{size}px;width:auto;height:auto;display:block'></div>"
        )
        page.evaluate("(h) => { document.body.innerHTML = h; }", html)
        page.wait_for_function("() => { const i = document.querySelector('img'); return i && i.complete && i.naturalWidth > 0; }", timeout=10000)
        box = page.query_selector("#box")
        assert box is not None
        return box.screenshot(omit_background=background is None, type="png")

    def render_png_wide(self, svg: str, width: int, height: int, background: str | None = None) -> bytes:
        page = self._ensure()
        bg = background or "transparent"
        html = (
            f"<div id='box' style='width:{width}px;height:{height}px;background:{bg};display:flex;align-items:center;justify-content:center'>"
            f"<img src='data:image/svg+xml;base64,{self._b64(svg)}' style='max-width:{width}px;max-height:{height}px;width:auto;height:auto;display:block'></div>"
        )
        page.evaluate("(h) => { document.body.innerHTML = h; }", html)
        page.wait_for_function("() => { const i = document.querySelector('img'); return i && i.complete && i.naturalWidth > 0; }", timeout=10000)
        box = page.query_selector("#box")
        assert box is not None
        return box.screenshot(omit_background=background is None, type="png")

    def render_gray(self, svg: str, size: int, background: str = "#FFFFFF") -> Gray:
        return self.render_gray_batch([svg], size, background)[0]

    def render_gray_batch(self, svgs: list[str], size: int, background: str = "#FFFFFF") -> list[Gray]:
        page = self._ensure()
        out: list[Gray] = []
        chunk = 64
        for i in range(0, len(svgs), chunk):
            part = [self._b64(s) for s in svgs[i:i + chunk]]
            res = page.evaluate(_GRAY_JS, [part, size, background])
            out.extend(res)
        return out

    def screenshot_html(self, html: str, width: int, height: int, full_page: bool = True) -> bytes:
        """لقطة لصفحة HTML كاملة (ورقة المعاينة) بلا نافذة."""
        assert self._browser is not None or self._ensure() is not None
        page = self._browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)  # type: ignore[union-attr]
        try:
            page.set_content(html, wait_until="load")
            page.wait_for_timeout(150)
            return page.screenshot(full_page=full_page, type="png")
        finally:
            page.close()

    def _file_page(self, path: Path, width: int, height: int = 900, scale: float = 1):
        assert self._browser is not None or self._ensure() is not None
        page = self._browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)  # type: ignore[union-attr]
        page.goto(path.resolve().as_uri(), wait_until="load")
        page.evaluate("() => document.fonts.ready")
        page.wait_for_timeout(200)
        return page

    def html_pdf(self, path: Path, landscape: bool = False) -> bytes:
        """ملف HTML محلي إلى PDF يحترم @page وأنماط الطباعة (A4 للدليل، و1920×1080 لعرض الكشف)؛ المسارات النسبية تُحمَّل من مجلده."""
        page = self._file_page(path, 1920 if landscape else 1200, 1080 if landscape else 900)
        try:
            if landscape:
                return page.pdf(width="1920px", height="1080px", print_background=True, prefer_css_page_size=True)
            return page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            page.close()

    def html_png(self, path: Path, width: int = 1280, height: int | None = None, scale: float = 1) -> bytes:
        """بلا height: الصفحة كاملة؛ بها: لقطة بمقاس الشاشة نفسه (شاشات المنتج)."""
        page = self._file_page(path, width, height or 900, scale)
        try:
            return page.screenshot(full_page=height is None, type="png")
        finally:
            page.close()

    def close(self) -> None:
        """إغلاق المتصفح آليًا؛ أخطاء الإغلاق تُكتم لأن العملية تنتهي على أي حال."""
        if self._browser is not None:
            with contextlib.suppress(Exception):
                self._browser.close()
        if self._pw is not None:
            with contextlib.suppress(Exception):
                self._pw.stop()
        self._browser = None
        self._pw = None
        self._page = None


def _json_safe(o):  # للمساعدة في الاختبار اليدوي
    return json.loads(json.dumps(o))
