import pytest

from sima.services import contrast, svgtools
from sima.services.colorize import colorize

SQUARE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect x="32" y="32" width="192" height="192" fill="#000000"/></svg>'


def test_contrast_values():
    assert contrast.contrast_ratio("#000000", "#FFFFFF") == 21.0
    assert contrast.contrast_ratio("#7A1C3E", "#F7F4EE") > 7
    assert contrast.passes(4.5, text=True) and not contrast.passes(4.4, text=True)
    assert contrast.passes(3.0, text=False)
    with pytest.raises(ValueError, match="غير صالح"):
        contrast.hex_to_rgb("blue")


def test_static_audit_passes_clean_svg():
    rep = svgtools.static_audit(SQUARE, allowed_colors={"#000000", "#FFFFFF"})
    assert rep.ok, rep.findings
    assert rep.shapes == 1 and rep.view_box == (0, 0, 256, 256)


@pytest.mark.parametrize("snippet,word", [
    ('<text x="10" y="10">أ</text>', "نص حي"),
    ('<defs><linearGradient id="g"/></defs>', "تدرج"),
    ('<filter id="f"/>', "فلتر"),
    ('<image href="x.png"/>', "صورة"),
    ('<rect width="10" height="10" fill="#FF0000"/>', "خارج المسموح"),
    ('<rect width="10" height="10" fill="#000" opacity="0.5"/>', "شفافية"),
])
def test_static_audit_flags_forbidden(snippet, word):
    svg = SQUARE.replace("</svg>", snippet + "</svg>")
    rep = svgtools.static_audit(svg, allowed_colors={"#000000", "#FFFFFF"})
    assert not rep.ok
    assert any(word in f for f in rep.findings), rep.findings


def test_static_audit_requires_viewbox_and_shapes():
    rep = svgtools.static_audit('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    assert "لا viewBox" in rep.findings and "لا أشكال مرسومة" in rep.findings
    assert not svgtools.static_audit("<svg").ok


def test_variants_are_valid_and_change_colors():
    mono = svgtools.mono(SQUARE, "#FFFFFF")
    assert 'fill="#FFFFFF"' in mono
    rev = svgtools.reversed_(SQUARE)
    root = svgtools.parse(rev)
    first = next(iter(root))
    assert first.get("data-role") == "background" and first.get("fill") == "#000000"
    assert 'fill="#FFFFFF"' in rev
    mir = svgtools.mirrored(SQUARE)
    assert "scale(-1 1)" in mir
    blur = svgtools.blurred_wrapper(SQUARE)
    assert "feGaussianBlur" in blur
    assert svgtools.strip_background(rev).count("<") == SQUARE.count("<") + 0 or "background" not in svgtools.strip_background(rev)


def test_recolor_and_colorize_with_accent():
    svg = SQUARE.replace("</svg>", '<circle cx="128" cy="128" r="20" fill="#000000" data-tone="accent"/></svg>')
    out = colorize(svg, "#7A1C3E", "#D9A441")
    assert out.count("#7A1C3E") == 1 and out.count("#D9A441") == 1
    out2 = colorize(svg, "#7A1C3E", None)
    assert out2.count("#7A1C3E") == 2
    assert svgtools.ensure_title(SQUARE, "x").count("<title>") == 1
