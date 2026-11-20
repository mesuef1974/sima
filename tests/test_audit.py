"""فحص الحرفية الآلي: الهامش واتزان مركز الكتلة (يسبقان حَكَمًا يردّ بهما مرارًا)."""
from __future__ import annotations

from sima.services.audit import AuditService

from .fakes import FakeRenderer, rect_svg


def run(svg: str):
    return AuditService(FakeRenderer()).audit("c1", svg)


def test_centered_block_with_margin_has_no_craft_warnings():
    rep = run(rect_svg(64, 64, 128, 128))
    assert not any("هامش" in w or "مركز كتلة" in w for w in rep.warnings)
    off = rep.metrics["centroid_offset_256"]
    assert abs(off["x"]) < 0.01 and abs(off["y"]) < 0.01


def test_block_touching_edge_warns_about_margin_below_four_percent():
    rep = run(rect_svg(5, 60, 140, 136))  # هامش أيسر نحو 2%
    assert any("هامش العلامة" in w for w in rep.warnings)


def test_off_center_mass_warns_with_direction():
    rep = run(rect_svg(150, 64, 90, 128))  # الكتلة نحو اليمين وهامشها كافٍ
    assert any("مركز كتلة الحبر" in w and "يمين" in w for w in rep.warnings)
    assert rep.metrics["centroid_offset_256"]["x"] > 0.08
