"""خطّا الهوية يعلنهما المالك في الموجز (قراره 2026-11-15: Tajawal): `identity.fonts` يغلب type في اتجاه التسليم
المعتمد من خارج الخط، فتتغيّر بصمة الاتجاه وتُفتح بوابته، ولا يمسّ الأصول المثبّتة. لا اتصال شبكي ولا نموذج."""
from __future__ import annotations

import pytest
import yaml

from sima import config
from sima.domain import brief_from_dict
from sima.domain.identity import CheckReport
from sima.services import adopt, designer, type_system

from .test_designer import _delivery, track  # noqa: F401
from .test_designer_track import _picked
from .test_domain_ledger_workspace import BRIEF

OWNER = ("2026-11-15", "ق")
TAJAWAL = {"heading": {"font": "Tajawal-Bold.ttf", "weight": 700}, "body": {"font": "Tajawal-Regular.ttf", "weight": 400}}


def _brief(**identity):
    return brief_from_dict({**BRIEF, "identity": {"scope": "core", "designer": "external", **identity}})


def test_fonts_parse_hash_and_require_an_outside_mark():
    plain, declared = _brief(), _brief(fonts=TAJAWAL)
    assert plain.identity.fonts is None and declared.identity.fonts == TAJAWAL
    assert plain.hash() != declared.hash()  # الإعلان مدخل للمفتاح: إصدار جديد
    assert brief_from_dict({**BRIEF, "identity": {"scope": "core", "designer": "external"}}).hash() == plain.hash()  # الغياب لا يغيّر
    for bad in ({"heading": TAJAWAL["heading"]}, {**TAJAWAL, "x": 1}, "Tajawal",
                {**TAJAWAL, "body": {"font": "../x.ttf", "weight": 400}},
                {**TAJAWAL, "body": {"font": "a.ttf", "weight": 5}},
                {**TAJAWAL, "body": {"font": "a.ttf"}}):
        with pytest.raises(ValueError, match=r"identity\.fonts"):
            _brief(fonts=bad)
    with pytest.raises(ValueError, match=r"identity\.fonts"):
        brief_from_dict({**BRIEF, "identity": {"scope": "core", "fonts": TAJAWAL}})  # بلا علامة من خارج الخط


def test_declared_fonts_override_the_delivered_type_and_move_the_digest(track):  # noqa: F811
    tmp, _brief0, _pipe, ws = _picked(track)
    designer.write_manifest(ws, 5, _delivery(tmp / "delivery"))
    path = designer.manifest_path(ws)
    base = adopt.load_manifest(path, "x", owner=OWNER)
    over = adopt.load_manifest(path, "x", owner=OWNER, fonts=TAJAWAL)
    assert over.direction["type"]["heading"] == TAJAWAL["heading"] and over.direction["type"]["body"] == TAJAWAL["body"]
    assert over.direction["type"].get("numerals") == base.direction["type"].get("numerals")
    assert over.digest != base.digest and over.min_mark_px == base.min_mark_px
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["direction"]["type"] == base.direction["type"]  # التسليم لا يُعدَّل


def test_tajawal_ships_with_its_license_and_passes_the_type_checks():
    for role, choice in (("العناوين", type_system.TypeChoice("Tajawal-Bold.ttf", 700)),
                         ("النص", type_system.TypeChoice("Tajawal-Regular.ttf", 400))):
        rep = CheckReport()
        type_system.check_type(config.FONTS_DIR, role, choice, "latn", rep)
        assert not rep.failures, rep.failures
        assert type_system.license_file(config.FONTS_DIR, choice.font).name == "OFL-Tajawal.txt"


def test_two_static_faces_of_one_family_keep_their_own_weights():
    from sima.services import brand_book, design_tokens

    two = {"heading": {"family": "Tajawal", "file": "Tajawal-Bold.ttf", "weight": 700},
           "body": {"family": "Tajawal", "file": "Tajawal-Regular.ttf", "weight": 400}}
    one = {"heading": {"family": "Reem Kufi", "file": "ReemKufi[wght].ttf", "weight": 700},
           "body": {"family": "IBM Plex Sans Arabic", "file": "IBMPlexSansArabic-Regular.ttf", "weight": 400}}
    assert (design_tokens.face_weight(two, "heading"), design_tokens.face_weight(two, "body")) == ("700", "400")
    assert design_tokens.face_weight(one, "heading") == design_tokens.face_weight(one, "body") == "100 1000"  # كما كان
    faces = brand_book._faces(two, "fonts/")
    assert "Tajawal-Bold.ttf\") format(\"truetype\");font-weight:700" in faces and "font-weight:400" in faces
    assert "font-weight:100 1000" in brand_book._faces(one, "fonts/")
