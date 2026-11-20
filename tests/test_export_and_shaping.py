import json
import struct

import pytest

from sima.config import FONTS_DIR
from sima.domain import Concept, Family, Medium, brief_from_dict
from sima.services import export, svgtools
from sima.services.shaping import ShapingService, _scale_path

from .fakes import FakeRenderer, rect_svg
from .test_domain_ledger_workspace import BRIEF


def test_build_ico_layout():
    pngs = {16: b"a" * 10, 32: b"b" * 20}
    ico = export.build_ico(pngs)
    assert ico[:6] == struct.pack("<HHH", 0, 1, 2)
    w, h, _, _, planes, bpp, size, off = struct.unpack("<BBBBHHII", ico[6:22])
    assert (w, h, planes, bpp, size, off) == (16, 16, 1, 32, 10, 6 + 32)
    assert ico[off:off + 10] == b"a" * 10 and len(ico) == 6 + 32 + 30


def test_tokens_webmanifest_vue():
    b = brief_from_dict(BRIEF)
    css = export.tokens_css(b, "demo")
    assert "--color-mark-ink: #7A1C3E" in css and ":root" in css
    m = json.loads(export.webmanifest(b, "#7A1C3E", "#F7F4EE"))
    assert m["dir"] == "rtl" and m["icons"][2]["purpose"] == "maskable"
    c = Concept("c1", "مربع", Family.ABSTRACT, Medium.ABSTRACT_MARK, "فكرة")
    svg = rect_svg(32, 32, 192, 192, '<circle cx="128" cy="128" r="24" fill="#000000" data-tone="accent"/>')
    vue = export.brand_mark_vue(svg, b, c)
    assert "data-tone" not in vue and "var(--color-mark-ink, #7A1C3E)" in vue and ':width="size"' in vue
    assert "<text" not in vue


def test_favicon_whitens_at_night_and_mark_comment_describes_the_symbol():
    """ط4 وط5 من «مسك» v10: الأيقونة تبيضّ على شريط تبويب داكن، وعنوانها اسم العلامة لا اسم المسودة، وviewBox بلا أصفار؛
    وتعليق BrandMark يصف الرمز وحده لا جملة الشعار الكامل. التطبيق مرتين كمرة (التسليم يعيده على حزمة مولَّدة به)."""
    b = brief_from_dict(BRIEF)
    src = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100.00000 100.00000" role="img"><title>knot-gap3</title>'
           '<path fill="#7A1C3E" d="M0 0H10V10Z"/></svg>')
    fav = export.favicon_svg(src, "شعار ديمو")
    assert export.NIGHT_FAVICON in fav and "knot-gap3" not in fav and "<title>شعار ديمو</title>" in fav
    assert 'viewBox="0 0 100 100"' in fav and export.favicon_svg(fav, "شعار ديمو") == fav
    stroked = export.favicon_svg('<svg viewBox="0 0 10 10"><circle r="2"/><path fill="none" stroke="#000" d="M0 0L9 9"/></svg>', "ت")
    assert "circle, ellipse" in stroked and '[fill="none"] { fill: none; }' in stroked
    c = Concept("a1", "شريط", Family.LITERAL, Medium.WORDMARK, "الاسم يتحوّل إلى شريط وDESIGN أسفله")
    vue = export.brand_mark_vue(src, b, c, lockup=True)
    assert "DESIGN" not in vue and "BrandLockup.vue" in vue and f"brand/{b.project}/favicon.svg" in vue
    assert 'viewBox="0 0 100 100"' in vue and export.mark_header(vue, b, "a1", True) == vue


def test_usage_states_the_declared_minimum_for_mark_and_lockup():
    """حدّ أدنى معلن فوق حجم الترويسة (96) يسري على القفل أيضًا، والأيقونات دونه مذكورة بأنها للتوافق فقط."""
    b = brief_from_dict(BRIEF)
    c = Concept("a1", "علامة رفيعة", Family.LITERAL, Medium.WORDMARK, "فكرة بجملة")
    low = export.usage_md(b, c, "demo", [], None, 24)
    assert "للرمز وحده 24 بكسل" in low and "للقفل مع الكلمة 24 بكسل" in low and "favicon دون هذا الحد (16 بكسل)" in low
    high = export.usage_md(b, c, "demo", [], None, 160)
    assert "للرمز وحده 160 بكسل" in high and "للقفل مع الكلمة 160 بكسل" in high
    assert "apple-touch-icon" in high.split("## المساحة الخالية")[1] and "بعلم المالك" in high
    assert "للتوافق" not in export.usage_md(b, c, "demo", [], None)


@pytest.mark.skipif(not (FONTS_DIR / "ReemKufi[wght].ttf").is_file(), reason="الخط غير موجود")
def test_arabic_wordmark_is_paths_only():
    from sima.adapters.font_shaper import HarfBuzzShaper
    svc = ShapingService(HarfBuzzShaper())
    wm = svc.wordmark("أوراق", "ReemKufi[wght].ttf", 700, title="أوراق")
    assert "<text" not in wm.svg and "<path" in wm.svg and wm.width > wm.height * 0.8
    rep = svgtools.static_audit(wm.svg, allowed_colors={"#000000", "#FFFFFF"})
    assert rep.ok, rep.findings
    wm2 = svc.wordmark("أوراق", "ReemKufi[wght].ttf", 700)
    assert wm.path_d == wm2.path_d  # حتمي
    lock = ShapingService.lockup(rect_svg(32, 32, 192, 192), wm, rtl=True)
    root = svgtools.parse(lock)
    ids = {el.get("id") for el in root.iter()}
    assert {"symbol", "wordmark"} <= ids


def test_scale_path():
    assert _scale_path("M 0 0 L 10 20 Z", 2, 1, 1) == "M 1 1 L 21 41 Z"


def test_export_service_writes_full_package(tmp_path):
    b = brief_from_dict(BRIEF)
    c = Concept("c1", "مربع", Family.ABSTRACT, Medium.ABSTRACT_MARK, "فكرة بجملة")
    r = FakeRenderer()
    pkg = export.ExportService(r).export(export.ExportInputs(b, c, rect_svg(32, 32, 192, 192), None, None, None, "<html></html>"), tmp_path / "package", 1)
    names = set(pkg.files)
    for n in ("demo-mark.svg", "demo-mark-mono.svg", "demo-mark-reversed.svg", "favicon.ico", "favicon.svg", "favicon-32.png",
              "apple-touch-icon.png", "icon-192.png", "icon-512.png", "maskable-512.png", "site.webmanifest", "tokens.css",
              "BrandMark.vue", "USAGE.md", "concept.json", "preview.html"):
        assert n in names, n
        assert (tmp_path / "package" / n).stat().st_size > 0
    usage = (tmp_path / "package" / "USAGE.md").read_text(encoding="utf-8")
    assert "قواعد استعمال" in usage and "WCAG" in usage
    assert "#7A1C3E" in (tmp_path / "package" / "demo-mark.svg").read_text(encoding="utf-8")


def test_lockup_keeps_the_marks_root_paint_and_frees_the_wordmark_id():
    """رمز اعتُمد من خارج الخط: لونه على جذره ومحتواه مغلَّف بمعرّف الكلمة. في القفل يبقى رمزًا ملوَّنًا، والكلمة ما يُشكَّل بجانبه."""
    from sima.services.colorize import colorize
    from sima.services.shaping import ShapingService, WordmarkSVG

    mark = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="188 8 720 660" fill="#000000"><g id="wordmark"><path d="M 200 20 H 400 V 300 Z"/>'
            '<path fill="none" stroke="#000000" stroke-width="1.5" d="M 300 40 L 500 400"/></g></svg>')
    word = WordmarkSVG(svg="", width=400.0, height=256.0, path_d="M 0 0 H 400 V 256 Z")
    lock = ShapingService.lockup(mark, word, rtl=True)
    assert lock.count('id="wordmark"') == 1 and '<g id="symbol" fill="#000000" transform=' in lock
    colored = colorize(lock, "#7A1C3E", "#D9A441")
    assert "#000000" not in colored and colored.count("#7A1C3E") == 3  # مجموعة الرمز وخطّه والكلمة قبل تحبيرها


def test_shaper_falls_back_to_glyph_parts_when_union_fails():
    """Cairo 600 بهذا النص يتعذّر على pathops توحيده كله فكان يرمي ويُسقط بناء لوحة الاتجاهات («مسك» v5، 2026-11-17)."""
    from sima.adapters.font_shaper import HarfBuzzShaper
    from sima.services.compose import visual_runs

    word = HarfBuzzShaper().shape(visual_runs("اذكر الخامة باسمها الصحيح؛"), "Cairo[slnt,wght].ttf", 600)
    assert word.path_d and word.advance > 0


def test_vue_component_drops_the_fixed_size_of_the_source_svg():
    """«مسك» v5: أصل المصمّم بمقاس ثابت (100mm) فخرج المكوّن بسمتَي عرض وارتفاع مكرّرتين ردّهما eslint المشروع."""
    out = export._vue_svg('<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="100mm" height="65mm" viewBox="0 0 100 65">'
                          '<path stroke-width="2" d="M0 0"/></svg>', '<svg class="brand-mark" :width="size" :height="size" ')
    assert out.startswith('<svg class="brand-mark" :width="size" :height="size" version="1.1" viewBox="0 0 100 65">')
    assert 'stroke-width="2"' in out and "100mm" not in out
