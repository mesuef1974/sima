"""عين الرسّام: معاينة حية لما يكتبه النموذج أثناء الاستدعاء.

الرسّام بلا Bash، فكان يكتب وصف العلامة ولا يرى ناتجها إلا في استدعاء لاحق؛ كل تصحيح بصري كلّف استدعاءً كاملًا. هنا يراقب
الخط `work/concepts` و`work/styles` أثناء عمل النموذج: كل `<id>.mark.yaml` يُكتب أو يتغيّر يُبنى ويُصيَّر إلى
`<id>.preview.png` بجانبه (ورقة: العلامة كبيرة، ومعكوسة، وبمقاسات صغيرة حقيقية)، وخطأ البناء يُكتب في `<id>.mark.error.txt`.
لا يُكتب `<id>.svg` هنا؛ بناؤه المعتمد يبقى لخطوة الخط بعد الاستدعاء. المعاينة عون للرسّام وليست مخرجًا.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import escape

from .. import config
from .ports import Renderer
from .svgtools import parse, view_box

FOLDERS = ("concepts", "styles", "thumbs")
SUFFIX = ".preview.png"
LIMIT_SUFFIX = ".preview.limit.txt"  # بلغ المفهوم حد معايناته في هذا الاستدعاء
SHEET_W, SHEET_H = 768, 512
SMALL_SIZES = (96, 48, 16)
_OPEN = re.compile(r"\s*(?:<\?xml[^>]*>\s*)?<svg\b[^>]*>", re.IGNORECASE)


def preview_path(spec: Path) -> Path:
    return spec.parent / (spec.name.removesuffix(".mark.yaml") + SUFFIX)


def sheet_svg(svg: str, caption: str) -> str:
    """ورقة معاينة واحدة 768×512: العلامة كبيرة على أبيض، ومعكوسة على أسود، وبارتفاعات 96 و48 و16 بكسل فعلية."""
    vb = view_box(parse(svg)) or (0.0, 0.0, float(config.CANVAS), float(config.CANVAS))
    m = _OPEN.match(svg)
    end = svg.rfind("</svg>")
    inner = svg[m.end():end] if m and end > 0 else ""
    box = f"{vb[0]:g} {vb[1]:g} {vb[2]:g} {vb[3]:g}"
    ratio = vb[2] / vb[3] if vb[3] else 1.0

    def nest(x: float, y: float, w: float, h: float) -> str:
        return f'<svg x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" viewBox="{box}">{inner}</svg>'

    parts = [f'<rect width="{SHEET_W}" height="{SHEET_H}" fill="#FFFFFF"/>', nest(16, 16, 480, 480),
             '<rect x="512" y="16" width="240" height="160" fill="#000000"/>',
             f'<g style="filter:invert(1)">{nest(524, 28, 216, 136)}</g>']
    y = 192.0
    for h in SMALL_SIZES:
        w = min(240.0, h * ratio)
        parts.append(nest(512, y, w, w / ratio if ratio else h))
        y += h + 16
    parts.append(f'<text x="752" y="500" text-anchor="end" font-family="sans-serif" font-size="14" fill="#666666">{escape(caption)}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SHEET_W} {SHEET_H}" width="{SHEET_W}" height="{SHEET_H}">'
            + "".join(parts) + "</svg>")


class LivePreview:
    """يُستدعى دوريًا بمجلد work/ أثناء عمل النموذج. أول نداء لكل مجلد لقطة بداية بلا تصيير. الملف يُصيَّر حين يثبت
    توقيعه بين نداءين متتاليين (لا يُبنى ملف ما زال يُكتب)، وتُحذف معاينته القديمة فور تغيّره كي لا تُقرأ صورة لا تطابقه.
    وحد المعاينات لكل بناء في الاستدعاء الواحد مفروض: `begin` في أول كل استدعاء يصفّر العدّاد (كان تراكميًّا عبر استدعاءات
    الأمر)، وبعد LIVE_PREVIEW_MAX معاينة لا تُصيَّر أخرى ويُكتب بجانب البناء سبب غيابها."""

    def __init__(self, renderer: Renderer, build: Callable[[str, str], str]):
        self._renderer = renderer
        self._build = build
        self._done: dict[Path, tuple[int, int]] = {}
        self._pending: dict[Path, tuple[int, int]] = {}
        self._count: dict[Path, int] = {}
        self._primed: set[Path] = set()

    def begin(self, work: Path) -> list[str]:
        """بداية استدعاء نموذج: عدّاد المعاينات يبدأ من صفر، وتُزال تنبيهات الحد السابقة، ثم لقطة البداية."""
        self._count.clear()
        for folder in FOLDERS:
            for p in (work / folder).glob("*" + LIMIT_SUFFIX) if (work / folder).is_dir() else []:
                p.unlink(missing_ok=True)
        return self(work)

    def __call__(self, work: Path) -> list[str]:
        first = work not in self._primed
        self._primed.add(work)
        rendered: list[str] = []
        for folder in FOLDERS:
            d = work / folder
            for spec in sorted(d.glob("*.mark.yaml")) if d.is_dir() else []:
                try:
                    st = spec.stat()
                except OSError:
                    continue
                sig = (st.st_mtime_ns, st.st_size)
                if first:
                    self._done[spec] = sig
                    continue
                if self._done.get(spec) == sig:
                    continue
                if self._pending.get(spec) != sig:
                    self._pending[spec] = sig
                    preview_path(spec).unlink(missing_ok=True)
                    continue
                self._pending.pop(spec, None)
                self._done[spec] = sig
                if self._count.get(spec, 0) >= config.LIVE_PREVIEW_MAX:
                    (spec.parent / (spec.name.removesuffix(".mark.yaml") + LIMIT_SUFFIX)).write_text(
                        f"بلغ هذا البناء حد المعاينات ({config.LIVE_PREVIEW_MAX}) في هذا الاستدعاء، فلا تُصيَّر له معاينة أخرى. أعِده إلى"
                        " آخر صيغة رأيتَ صورتها أو سلّمه كما هو؛ الخط يبنيه ويفحصه بعد الاستدعاء.", encoding="utf-8")
                    continue
                self._render(spec)
                rendered.append(f"{folder}/{spec.name.removesuffix('.mark.yaml')}")
        return rendered

    def _render(self, spec: Path) -> None:
        sid = spec.name.removesuffix(".mark.yaml")
        err = spec.parent / f"{sid}.mark.error.txt"
        out = preview_path(spec)
        try:
            svg = self._build(spec.read_text(encoding="utf-8"), sid)
        except Exception as exc:  # noqa: BLE001 — خطأ البناء رسالة للرسّام لا انهيار للخط
            err.write_text(str(exc), encoding="utf-8")
            out.unlink(missing_ok=True)
            return
        err.unlink(missing_ok=True)
        self._count[spec] = n = self._count.get(spec, 0) + 1
        out.write_bytes(self._renderer.render_png(sheet_svg(svg, f"{sid} #{n}"), SHEET_W, "#FFFFFF"))


def clear(folder: Path) -> None:
    """يحذف معاينات مجلد (عند أرشفة المفاهيم): المعاينة لا تبقى بعد زوال بنائها."""
    for p in [*folder.glob("*" + SUFFIX), *folder.glob("*" + LIMIT_SUFFIX)] if folder.is_dir() else []:
        p.unlink(missing_ok=True)


def lines(folder: str = "concepts") -> list[str]:
    """تعليمات المعاينة الحية في طلبات الرسم والصقل والنقد."""
    if not config.LIVE_PREVIEW:
        return []
    return [
        "## عينك أثناء الرسم (معاينة حية)",
        f"في الاستدعاء الآلي تبني الأداة كل `work/{folder}/<id>.mark.yaml` تكتبه أو تعدّله وتصيّره خلال ثوانٍ إلى",
        f"`work/{folder}/<id>.preview.png`: العلامة كبيرة، ومعكوسة على أسود، وبارتفاعات 96 و48 و16 بكسل، ورقم المعاينة في الركن.",
        "- بعد كل كتابة افتح الصورة بـ Read وانظر إليها فعلًا. إن لم توجد بعد فاقرأها ثانية؛ وإن بقيت غائبة فاقرأ",
        "  `<id>.mark.error.txt` وأصلح البناء.",
        "- قارن ما تراه بما قصدته: هل تُقرأ الكلمة من النظرة الأولى؟ هل الحيلة ظاهرة بلا شرح؟ هل الكتلة متزنة والفراغات",
        "  متساوية بصريًا؟ هل يصمد الشكل عند 16؟ ما تراه العين هو الحكم لا الأرقام التي كتبتها.",
        f"- صحّح وأعد حتى ترضى عنه كمصمم محترف، بحد أقصى {config.LIVE_PREVIEW_MAX} معاينات للمفهوم في الاستدعاء: بعدها لا تُصيَّر"
        f" معاينة ويُكتب `<id>{LIMIT_SUFFIX}`، فلا تعدّل البناء بعد معاينته الأخيرة. لا تسلّم بناءً لم ترَ صورته.", "",
    ]
