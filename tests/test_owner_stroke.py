"""حدّ السماكة الذي يعلنه المالك (قراره 2026-11-15 على شعار «الشحانية» الرفيع المطابق للسكتش): بيان الاعتماد يحمل
`min_stroke_px` بيد المالك وحدها، فيفحصه الخط عنده بدل 1.5 ويُذكر في USAGE.md. لا اتصال شبكي ولا نموذج."""
from __future__ import annotations

import pytest
import yaml

from sima.domain import Concept, Family, Medium, brief_from_dict
from sima.services import adopt, designer, export
from sima.services.audit import AuditReport, AuditService

from .fakes import FakeRenderer, rect_svg
from .test_designer import _delivery, track  # noqa: F401
from .test_designer_track import _picked
from .test_domain_ledger_workspace import BRIEF

THIN = rect_svg(100, 60, 20, 136)  # خط رأسي رفيع: نحو 1.25 بكسل عند 16
OWNER = ("2026-11-15", "ق")


def _audit(**kw):
    return AuditService(FakeRenderer()).audit("c1", THIN, **kw)


def _manifest(ws) -> dict:
    return yaml.safe_load(designer.manifest_path(ws).read_text(encoding="utf-8"))


def test_audit_uses_the_owner_floor_instead_of_the_default():
    default = _audit()
    thick = default.metrics["min_stroke_px"]
    assert 0.9 < thick < 1.45 and not default.passed and "أقل من 1.5" in " ".join(default.findings)
    assert _audit(min_stroke=thick).passed  # الحد المعلن يغلب 1.5
    rep = _audit(min_stroke=thick + 1.0)
    assert not rep.passed and f"أقل من {thick + 1.0:g}" in " ".join(rep.findings)


def test_declaring_a_stroke_floor_is_validated_recorded_and_carried(track):  # noqa: F811
    tmp, _brief, _pipe, ws = _picked(track)
    folder = _delivery(tmp / "delivery")
    designer.write_manifest(ws, 5, folder)
    assert "min_stroke_px" not in _manifest(ws) and designer.declared_stroke(ws, 5) is None
    base = adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER).digest

    for bad in (0.5, 1.5, 2):
        with pytest.raises(designer.DesignerError):
            designer.write_manifest(ws, 5, folder, min_stroke_px=bad)

    designer.write_manifest(ws, 5, folder, min_stroke_px=1.25)
    assert (_manifest(ws)["min_stroke_px"], _manifest(ws)["min_stroke_px_by"]) == (1.25, "owner")
    loaded = adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)
    assert loaded.min_stroke_px == 1.25 and loaded.digest != base  # الإعلان يغيّر بصمة المحتوى فتُفحص العلامة من جديد

    designer.write_manifest(ws, 5, folder)  # تسليم لاحق بلا إعلان: القرار يُحمل
    assert _manifest(ws)["min_stroke_px"] == 1.25
    designer.write_manifest(ws, 4, folder)  # سكتش آخر: لا يُحمل إليه
    assert "min_stroke_px" not in _manifest(ws)


def test_a_hand_written_value_outside_the_range_is_refused(track):  # noqa: F811
    tmp, _brief, _pipe, ws = _picked(track)
    designer.write_manifest(ws, 5, _delivery(tmp / "delivery"))
    data = _manifest(ws)
    for bad in (0.4, 1.5, "x"):
        text = yaml.safe_dump({**data, "min_stroke_px": bad}, allow_unicode=True, sort_keys=False)
        designer.manifest_path(ws).write_text(text, encoding="utf-8")
        with pytest.raises(adopt.AdoptError, match="min_stroke_px"):
            adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)


def test_usage_and_fingerprint_name_the_floor_the_owner_declared():
    b = brief_from_dict(BRIEF)
    c = Concept("a1", "علامة رفيعة", Family.LITERAL, Medium.WORDMARK, "فكرة بجملة")
    audit = AuditReport(concept_id="a1", passed=True, metrics={"base_size": 192, "min_stroke_px": 1.29})
    default = export.usage_md(b, c, "demo", [], audit)
    assert "(الحد 1.5)." in default
    declared = export.usage_md(b, c, "demo", [], audit, 192, min_stroke_px=1.25)
    assert "(الحد 1.25 يعلنه المالك بدل 1.5" in declared

    def stamp(**kw) -> str:
        return export.ExportInputs(b, c, "<svg/>", None, None, None, None, **kw).fingerprint(1)

    assert stamp() == stamp(min_stroke_px=None) != stamp(min_stroke_px=1.25)  # بلا إعلان تبقى البصمات كما كانت
