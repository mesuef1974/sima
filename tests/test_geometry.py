"""أداة البناء الهندسي: الوصف يولّد SVG حتميًا، والأخطاء رسائل عربية لا انهيار."""
import pytest
import yaml

from sima.adapters.geometry import ConstructError, build_svg
from sima.services import protocol

SPEC = """canvas: 256
defs:
  disc: {circle: [128, 128, 104]}
  hole: {circle: [128, 128, 52]}
  bar: {rect: [116, 10, 24, 90], r: 4, rotate: 30}
  petal: {ellipse: [128, 60, 14, 28]}
mark: {round: {difference: [disc, hole, bar, {repeat: petal, n: 6}]}, r: 4}
accent: {circle: [128, 128, 70]}
"""


def test_build_is_deterministic_clean_and_tags_accent():
    a, b = build_svg(SPEC, "اختبار"), build_svg(SPEC, "اختبار")
    assert a == b and a.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><title>اختبار</title>')
    assert a.count("<path") == 2 and 'data-tone="accent"' in a
    assert "<text" not in a and "Gradient" not in a and "filter" not in a
    import re
    assert not re.search(r"\d\.\d{3}", a)  # منزلتان عشريتان على الأكثر


@pytest.mark.parametrize(("spec", "msg"), [
    ("mark: {circle: [1, 2]}", "3 أرقام"),
    ("defs: {a: {star: 1}}\nmark: a", "مفتاح شكل"),
    ("mark: b", "غير معرّف"),
    ("mark: {difference: [{circle: [10, 10, 5]}, {circle: [10, 10, 50]}]}", "فارغ"),
    ("mark: {arc: [128, 128, 60], from: 0, to: 90}", "width"),
    ("mark: {repeat: {circle: [1, 1, 1]}, n: 500}", "بين 2"),
    ("mark: {circle: [1, 1, 1e9]}", "خارج الحدود"),
    ("mark: {path: 'L 3 4'}", "يبدأ"),
])
def test_bad_specs_give_arabic_errors(spec, msg):
    with pytest.raises(ConstructError, match=msg):
        build_svg(spec, "x")


def test_compile_marks_writes_svg_and_reports_errors(tmp_path):
    from sima.domain import Medium, brief_from_dict
    from sima.services.workspace import open_workspace

    from .test_domain_ledger_workspace import BRIEF
    ws = open_workspace(tmp_path, brief_from_dict(BRIEF))
    ws.ensure()
    (ws.work / "concepts.yaml").write_text(yaml.safe_dump({"concepts": [{"id": "c1", "name": "حلقة", "family": "abstract"},
                                                                       {"id": "c2", "name": "ب", "family": "literal"}]},
                                                          allow_unicode=True), encoding="utf-8")
    (ws.concepts_dir / "c1.mark.yaml").write_text(SPEC, encoding="utf-8")
    (ws.concepts_dir / "c2.mark.yaml").write_text("mark: {circle: [1]}", encoding="utf-8")
    (ws.concepts_dir / "c2.svg").write_text("<svg/>", encoding="utf-8")
    errs = protocol.compile_marks(ws, build_svg)
    assert set(errs) == {"c2"} and "<title>حلقة</title>" in (ws.concepts_dir / "c1.svg").read_text(encoding="utf-8")
    assert not (ws.concepts_dir / "c2.svg").exists() and (ws.concepts_dir / "c2.mark.error.txt").is_file()
    mtime = (ws.concepts_dir / "c1.svg").stat().st_mtime_ns
    protocol.compile_marks(ws, build_svg)
    assert (ws.concepts_dir / "c1.svg").stat().st_mtime_ns == mtime  # لا كتابة بلا تغيير
    v = protocol.validate_diverge(ws, Medium.ABSTRACT_MARK, construct=True)
    assert any("خطأ في بناء" in p and "c2" in p for p in v.problems)


def test_closed_quadratic_contours_serialize():
    """تقليص دائرة وتمديدها يولّد كفافًا تربيعيًا مغلقًا بنقاط ضمنية؛ كان يُسقط البناء كله."""
    svg = build_svg("mark: {round: {offset: {circle: [128, 128, 80]}, d: 12}, r: 10}\naccent: {circle: [128, 128, 40]}", "د")
    assert svg.count("<path") == 2 and "None" not in svg


def test_fit_crops_wide_wordmark_to_ink_with_margin():
    spec = "width: 600\nheight: 256\nfit: 0.1\nmark: {rect: [100, 50, 300, 100]}"
    svg = build_svg(spec, "ك")
    assert 'viewBox="0 0 320 120"' in svg and "M10 10" in svg


def test_text_shape_uses_licensed_font_and_parts():
    from sima.adapters.font_shaper import shape_parts
    spec = ('width: 640\nheight: 320\nfit: 0.1\ndefs:\n'
            '  w: {text: "سِمة", font: "Cairo[slnt,wght].ttf", weight: 900, size: 160, at: [40, 200], part: letters}\n'
            '  k: {text: "سِمة", font: "Cairo[slnt,wght].ttf", weight: 900, size: 160, at: [40, 200], part: marks}\n'
            'mark: {union: [w, k]}\naccent: k\n')
    svg = build_svg(spec, "t")
    assert 'data-tone="accent"' in svg and "<text" not in svg
    full = shape_parts("سِمة", "Cairo[slnt,wght].ttf", 900, 160, 40, 200)
    dots = shape_parts("سِمة", "Cairo[slnt,wght].ttf", 900, 160, 40, 200, "dots")
    marks = shape_parts("سِمة", "Cairo[slnt,wght].ttf", 900, 160, 40, 200, "marks")
    assert 0 < abs(dots.area) < 0.2 * abs(full.area) and 0 < abs(marks.area) < 0.05 * abs(full.area)
    with pytest.raises(ConstructError):
        build_svg('mark: {text: "سمة", font: "../x.ttf"}', "t")
    with pytest.raises(ConstructError):
        build_svg('mark: {text: "سم", font: "Cairo[slnt,wght].ttf", part: dots}', "t")  # بلا نقاط


def test_parts_follow_unicode_origin_in_every_project_font():
    """ريم كوفي يفصل نقطتي التاء حرفًا مستقلًا صنفه في الخط mark: هما نقاط لا حركة، والكسرة وحدها حركة."""
    from sima.adapters.font_shaper import shape_parts
    for font, w in (("ReemKufi[wght].ttf", 700), ("Cairo[slnt,wght].ttf", 900), ("Almarai-ExtraBold.ttf", 800),
                    ("IBMPlexSansArabic-Bold.ttf", 700)):
        area = {p: abs(shape_parts("سِمة", font, w, 160, 40, 200, p).area) for p in ("all", "letters", "marks", "dots")}
        assert area["dots"] > 0 and area["marks"] > 0, font
        assert abs(area["all"] - area["letters"] - area["marks"]) < 0.01 * area["all"], font  # الحروف والحركات تقسمان الكلمة
        assert area["dots"] < 0.2 * area["letters"], font
        assert abs(shape_parts("سم", font, w, 160, 40, 200, "dots").area) == 0, font  # فراغ الميم ليس نقطة


def test_offset_miter_keeps_corners_sharp_for_heavy_letters():
    """التثقيل بزوايا حادة (حروف كوفية ومضغوطة): join=miter لا يدوّر، والافتراضي round يدوّر، والقيمة الغريبة خطأ عربي."""
    base = "mark: {offset: {rect: [80, 80, 96, 96]}, d: 8%s}"
    sharp, soft = build_svg(base % ", join: miter", "ح"), build_svg(base % "", "د")
    assert 'd="M184 72L184 184L72 184L72 72L184 72Z"' in sharp and "Q" in soft
    with pytest.raises(ConstructError, match="join"):
        build_svg(base % ", join: wavy", "خ")
