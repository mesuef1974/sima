"""أصغر عرض للشعار الكامل يعلنه المالك (قراره 2026-11-20 لـ«مسك»): حين يصير الرمز أيقونة منفصلة بحدّ 16 يبقى حدّ الشعار
الكامل في بيان الاعتماد (`min_wordmark_px`) ويُذكر في USAGE.md ويدخل البصمات. لا اتصال شبكي ولا نموذج."""
from __future__ import annotations

import pytest
import yaml

from sima.domain import Concept, Family, Medium, brief_from_dict
from sima.services import adopt, designer, export

from .test_designer import _delivery, track  # noqa: F401
from .test_designer_track import _picked
from .test_domain_ledger_workspace import BRIEF

OWNER = ("2026-11-20", "ق")


def _rewrite(ws, **kw) -> None:
    path = designer.manifest_path(ws)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    path.write_text(yaml.safe_dump({**data, **kw}, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_manifest_carries_the_declared_wordmark_width_into_the_digest(track):  # noqa: F811
    tmp, _brief, _pipe, ws = _picked(track)
    designer.write_manifest(ws, 5, _delivery(tmp / "delivery"))
    base = adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)
    assert base.min_wordmark_px is None
    _rewrite(ws, min_wordmark_px=280)
    declared = adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)
    assert declared.min_wordmark_px == 280 and declared.digest != base.digest
    for bad in (8, "x"):
        _rewrite(ws, min_wordmark_px=bad)
        with pytest.raises(adopt.AdoptError, match="min_wordmark_px"):
            adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)


def test_usage_and_fingerprint_name_the_wordmark_width():
    b = brief_from_dict(BRIEF)
    c = Concept("a1", "رمز", Family.LITERAL, Medium.WORDMARK, "فكرة بجملة")
    assert "الشعار الكامل" not in export.usage_md(b, c, "demo", [], None)
    assert "لا يقل عرضه عن 280 بكسل" in export.usage_md(b, c, "demo", [], None, min_wordmark_px=280)

    def stamp(**kw) -> str:
        return export.ExportInputs(b, c, "<svg/>", None, None, None, None, **kw).fingerprint(1)

    assert stamp() == stamp(min_wordmark_px=None) != stamp(min_wordmark_px=280)


def test_declared_wordmark_stroke_needs_the_width_and_enters_the_digest(track):  # noqa: F811
    tmp, _brief, _pipe, ws = _picked(track)
    designer.write_manifest(ws, 5, _delivery(tmp / "delivery"))
    _rewrite(ws, min_wordmark_px=280)
    width = adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)
    _rewrite(ws, min_wordmark_stroke_px=1.25)
    both = adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)
    assert width.min_wordmark_stroke_px is None and both.min_wordmark_stroke_px == 1.25 and both.digest != width.digest
    for bad in (0.5, 1.5, "x"):
        _rewrite(ws, min_wordmark_stroke_px=bad)
        with pytest.raises(adopt.AdoptError, match="min_wordmark_stroke_px"):
            adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)
    _rewrite(ws, min_wordmark_px=None, min_wordmark_stroke_px=1.25)
    with pytest.raises(adopt.AdoptError, match="لا يُعلن بلا min_wordmark_px"):
        adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)



def test_brand_wordmark_color_keeps_the_lockup_in_one_colour(track):  # noqa: F811
    """«مسك» v10 (قرار المالك 2026-11-20: «العنابي»): `wordmark_color: brand` لا يغلّف الكلمة بـid="wordmark"، فلا يلوّنها
    التصدير بالحبر ويبقى الشعار كله بلون العلامة؛ والقيمة تدخل البصمة وغيرها يُرفض."""
    tmp, _brief, _pipe, ws = _picked(track)
    designer.write_manifest(ws, 5, _delivery(tmp / "delivery"))
    ink = adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)
    assert ink.wordmark_color == "ink" and 'id="wordmark"' in ink.wordmark
    _rewrite(ws, wordmark_color="brand")
    brand = adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)
    assert brand.wordmark_color == "brand" and 'id="wordmark"' not in brand.wordmark and brand.digest != ink.digest
    lock = export._wordmark_ink(brand.wordmark.replace("#000000", "#68112F"), "#68112F", "#35242C")
    assert "#35242C" not in lock
    _rewrite(ws, wordmark_color="gold")
    with pytest.raises(adopt.AdoptError, match="wordmark_color"):
        adopt.load_manifest(designer.manifest_path(ws), "x", owner=OWNER)
